"""
ARO Web Server
==============
Flask backend serving the ARO web UI.
Provides API endpoints for running research sessions, streaming progress,
and retrieving past session reports.
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

from flask import Flask, jsonify, request, Response, send_from_directory

# Ensure aro/ is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AROConfig
from memory.memory_service import MemoryService
from runtime.model_gateway import ModelGateway
from runtime.logger import SessionLogger
from agents.orchestrator import Orchestrator

app = Flask(__name__, static_folder="ui/dist", static_url_path="")

# In-memory session progress tracking
_progress_queues: dict[str, Queue] = {}
_session_status: dict[str, dict] = {}

logger = logging.getLogger("aro.web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


# ─── Patched logger that emits SSE events ────────────────────────────
class SSESessionLogger(SessionLogger):
    """Extended SessionLogger that pushes agent events to an SSE queue."""

    def __init__(self, log_dir: str, session_id: str, mode: str, queue: Queue):
        super().__init__(log_dir=log_dir, session_id=session_id, mode=mode)
        self._queue = queue

    def save_iteration_log(self, log):
        filepath = super().save_iteration_log(log)
        # Push iteration completion event
        self._queue.put({
            "type": "iteration_complete",
            "iteration": log.iteration,
            "metrics": log.metrics,
        })
        return filepath

    def save_final_report(self, report):
        filepath = super().save_final_report(report)
        data = report.model_dump(mode="json") if hasattr(report, "model_dump") else report
        self._queue.put({
            "type": "complete",
            "report": data,
        })
        return filepath


# Monkey-patch Orchestrator._run_agent_logged to emit SSE events
_original_run_agent_logged = Orchestrator._run_agent_logged

def _patched_run_agent_logged(self, agent, prompt, iter_log, context=None):
    queue = getattr(self, "_sse_queue", None)
    if queue:
        queue.put({
            "type": "agent_start",
            "agent": agent.name,
            "iteration": getattr(self, "_current_iteration", 0),
        })
    result = _original_run_agent_logged(self, agent, prompt, iter_log, context)
    if queue:
        queue.put({
            "type": "agent_done",
            "agent": agent.name,
        })
    return result

Orchestrator._run_agent_logged = _patched_run_agent_logged


def _run_research(session_id: str, objective: str, mode: str,
                  max_iterations: int, runtime_mode: str):
    """Background thread: run the orchestrator and stream progress."""
    queue = _progress_queues[session_id]
    base_dir = Path(__file__).resolve().parent
    config = AROConfig()
    config.mode = runtime_mode

    if max_iterations:
        config.max_iterations = max_iterations

    logs_root = str(base_dir / config.log_dir)

    try:
        memory = MemoryService(
            db_path=str(base_dir / config.db_path),
            session_id=session_id,
        )
        gateway = ModelGateway(config=config, session_id=session_id, log_dir=logs_root)
        session_logger = SSESessionLogger(
            log_dir=logs_root,
            session_id=session_id,
            mode=config.mode,
            queue=queue,
        )
        orchestrator = Orchestrator(config, memory, gateway, session_logger)
        orchestrator._sse_queue = queue

        _session_status[session_id] = {"status": "running", "objective": objective}

        report = orchestrator.run(research_objective=objective, mode=mode)

        _session_status[session_id]["status"] = "complete"

    except Exception as exc:
        logger.exception("Research session %s failed", session_id)
        queue.put({"type": "error", "message": str(exc)})
        _session_status[session_id] = {"status": "error", "error": str(exc)}
    finally:
        try:
            memory.close()
        except Exception:
            pass
        queue.put({"type": "done"})


# ─── API Endpoints ───────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def start_research():
    data = request.get_json(force=True)
    objective = data.get("objective", "").strip()
    if not objective:
        return jsonify({"error": "objective is required"}), 400

    mode = data.get("mode", "autonomous")
    max_iterations = data.get("max_iterations", None)
    runtime_mode = data.get("runtime_mode", "production")
    session_id = f"session_{uuid.uuid4().hex[:12]}"

    queue = Queue()
    _progress_queues[session_id] = queue
    _session_status[session_id] = {"status": "starting", "objective": objective}

    thread = threading.Thread(
        target=_run_research,
        args=(session_id, objective, mode, max_iterations, runtime_mode),
        daemon=True,
    )
    thread.start()

    return jsonify({"session_id": session_id})


@app.route("/api/stream/<session_id>")
def stream_progress(session_id):
    queue = _progress_queues.get(session_id)
    if not queue:
        return jsonify({"error": "session not found"}), 404

    def generate():
        while True:
            try:
                event = queue.get(timeout=300)
            except Exception:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/sessions")
def list_sessions():
    base_dir = Path(__file__).resolve().parent
    logs_dir = base_dir / "logs"
    sessions = []

    if logs_dir.exists():
        for session_dir in sorted(logs_dir.iterdir(), reverse=True):
            if not session_dir.is_dir() or not session_dir.name.startswith("session_"):
                continue
            report_file = session_dir / "final_report.json"
            if report_file.exists():
                try:
                    with open(report_file) as f:
                        report = json.load(f)
                    sessions.append({
                        "session_id": session_dir.name,
                        "objective": report.get("research_objective", ""),
                        "confidence": report.get("final_hypothesis_confidence", 0),
                        "risk": report.get("final_epistemic_risk", 0),
                        "novelty": report.get("final_novelty_score", 0),
                        "iterations": report.get("total_iterations", 0),
                        "tokens": report.get("total_tokens_used", 0),
                        "time": report.get("total_execution_time_seconds", 0),
                        "termination": report.get("termination_reason", ""),
                        "created_at": report.get("created_at", ""),
                    })
                except (json.JSONDecodeError, OSError):
                    continue

    return jsonify(sessions)


@app.route("/api/report/<session_id>")
def get_report(session_id):
    base_dir = Path(__file__).resolve().parent
    report_file = base_dir / "logs" / session_id / "final_report.json"

    if not report_file.exists():
        return jsonify({"error": "report not found"}), 404

    with open(report_file) as f:
        report = json.load(f)

    return jsonify(report)


# ─── Serve React App ─────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path):
    dist_dir = os.path.join(app.static_folder)
    if path and os.path.exists(os.path.join(dist_dir, path)):
        return send_from_directory(dist_dir, path)
    return send_from_directory(dist_dir, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
