"""
ARO MCP Server
==============
Exposes the research engine to any MCP client (Claude Desktop, Claude
Code, Cursor, ...) as tools and resources.

Tools:
- fast_research(question)                     ~15-30s single-pass answer
- deep_research(question, mode, max_iterations) full iterative pipeline
- list_research_sessions()                    past sessions + scores
- get_research_report(session_id)             full structured report

Resources:
- aro://reports/{session_id}                  final report JSON

Transports:
    python -m mcp_server.server               # stdio (local clients)
    python -m mcp_server.server --http        # streamable HTTP (remote)

Register with Claude Code (local):
    claude mcp add aro -- python -m mcp_server.server
Remote (after deploying with --http):
    claude mcp add --transport http aro https://<host>:8001/mcp
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastmcp import FastMCP

from config import AROConfig
from graph import GraphServices, build_fast_graph, build_research_graph
from memory.memory_service import MemoryService
from runtime.logger import SessionLogger

SESSION_ID_RE = re.compile(r"^session_[a-f0-9]{12}$")
LOGS_DIR = BASE_DIR / "logs"

mcp = FastMCP(
    "aro-research",
    instructions=(
        "ARO is an autonomous multi-agent research engine. Use fast_research "
        "for quick answers (~30s). Use deep_research for rigorous multi-"
        "iteration investigation with claim extraction, skeptic review, and "
        "confidence/risk scoring (minutes). Reports persist across calls."
    ),
)


def _services(session_id: str, mode: str) -> GraphServices:
    config = AROConfig()
    memory = MemoryService(
        db_path=str(BASE_DIR / config.db_path),
        session_id=session_id,
        vector_store_path=str(BASE_DIR / config.vector_store_path),
        enable_cross_session_memory=config.enable_cross_session_memory,
    )
    session_logger = SessionLogger(
        log_dir=str(LOGS_DIR), session_id=session_id,
        mode="fast" if mode == "fast" else config.mode,
    )
    return GraphServices(config=config, memory=memory, session_logger=session_logger)


def _summarize(report: dict) -> dict:
    """Compact tool response; the full report stays available by session id."""
    return {
        "session_id": report.get("session_id"),
        "answer": report.get("conclusion") or report.get("executive_summary"),
        "executive_summary": report.get("executive_summary"),
        "confidence": report.get("final_hypothesis_confidence"),
        "epistemic_risk": report.get("final_epistemic_risk"),
        "novelty": report.get("final_novelty_score"),
        "iterations": report.get("total_iterations"),
        "termination_reason": report.get("termination_reason"),
        "knowledge_gaps": [
            g.get("description") for g in report.get("knowledge_gaps", [])
        ][:5],
        "innovation_proposals": [
            {"title": p.get("title"), "novelty": p.get("novelty_interpretation")}
            for p in report.get("innovation_proposals") or []
        ],
        "hint": "Call get_research_report(session_id) for the full structured report.",
    }


@mcp.tool
def fast_research(question: str) -> dict:
    """Answer a research question with a single-pass web-grounded analysis
    (~15-30 seconds). Best for quick factual or overview questions."""
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    services = _services(session_id, "fast")
    try:
        graph = build_fast_graph(services)
        result = graph.invoke(
            {"objective": question, "tokens_used": 0, "started_at": time.time()},
        )
        return _summarize(result["final_report"].model_dump(mode="json"))
    finally:
        services.memory.close()


@mcp.tool
def deep_research(
    question: str,
    mode: str = "autonomous",
    max_iterations: int = 5,
) -> dict:
    """Run the full iterative research pipeline: planning, multi-engine web
    search, claim extraction, skeptic review, hypothesis synthesis, and
    mathematical confidence/risk scoring. Takes minutes. mode='innovation'
    additionally generates prior-art-scanned innovation proposals."""
    if mode not in ("autonomous", "innovation"):
        raise ValueError("mode must be 'autonomous' or 'innovation'")
    max_iterations = max(1, min(int(max_iterations), 10))

    session_id = f"session_{uuid.uuid4().hex[:12]}"
    services = _services(session_id, mode)
    services.config.max_iterations = max_iterations
    try:
        services.memory.create_session(question, mode)
        graph = build_research_graph(services)
        result = graph.invoke(
            {
                "objective": question, "mode": mode, "hitl": False,
                "iteration": 1, "tokens_used": 0, "last_token_snapshot": 0,
            },
            {"recursion_limit": 600},
        )
        return _summarize(result["final_report"].model_dump(mode="json"))
    finally:
        services.memory.close()


@mcp.tool
def list_research_sessions(limit: int = 20) -> list:
    """List past research sessions with their objectives and final scores."""
    sessions = []
    if LOGS_DIR.exists():
        for session_dir in sorted(LOGS_DIR.iterdir(), reverse=True):
            if not session_dir.name.startswith("session_"):
                continue
            report_file = session_dir / "final_report.json"
            if not report_file.exists():
                continue
            try:
                report = json.loads(report_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            sessions.append({
                "session_id": session_dir.name,
                "objective": report.get("research_objective", ""),
                "confidence": report.get("final_hypothesis_confidence", 0),
                "risk": report.get("final_epistemic_risk", 0),
                "iterations": report.get("total_iterations", 0),
                "created_at": report.get("created_at", ""),
            })
            if len(sessions) >= max(1, min(int(limit), 100)):
                break
    return sessions


def _load_report(session_id: str) -> dict:
    if not SESSION_ID_RE.match(session_id):
        raise ValueError("invalid session id")
    report_file = LOGS_DIR / session_id / "final_report.json"
    if not report_file.exists():
        raise ValueError(f"no report found for {session_id}")
    return json.loads(report_file.read_text())


@mcp.tool
def get_research_report(session_id: str) -> dict:
    """Fetch the full structured report (hypotheses, claims, gaps, metrics)
    for a past research session."""
    return _load_report(session_id)


@mcp.resource("aro://reports/{session_id}")
def report_resource(session_id: str) -> str:
    """Final report JSON for a research session."""
    return json.dumps(_load_report(session_id), indent=2, default=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="ARO MCP server")
    parser.add_argument(
        "--http", action="store_true",
        help="Serve streamable HTTP instead of stdio (for remote clients).",
    )
    parser.add_argument("--host", default=os.getenv("ARO_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("ARO_MCP_PORT", "8001")),
    )
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    main()
