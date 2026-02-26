"""
ARO Web Server
==============
Flask backend serving the ARO web UI.
Provides API endpoints for running research sessions, streaming progress,
and retrieving past session reports.
"""

import hmac
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS

# Ensure aro/ is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AROConfig
from memory.memory_service import MemoryService
from runtime.model_gateway import ModelGateway
from runtime.logger import SessionLogger
from agents.orchestrator import Orchestrator

app = Flask(__name__, static_folder="ui/dist", static_url_path="")
# SEC-008: Explicitly configure CORS to allow only known origins
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]}})

# In-memory session progress tracking
_progress_queues: dict[str, Queue] = {}
_session_status: dict[str, dict] = {}

logger = logging.getLogger("aro.web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# ─── Security Constants ──────────────────────────────────────────────
SESSION_ID_RE = re.compile(r'^session_[a-f0-9]{12}$')
_ARO_API_KEY = os.getenv("ARO_API_KEY", "")
MAX_CONCURRENT_SESSIONS = int(os.getenv("ARO_MAX_CONCURRENT", "3"))
MAX_ITERATIONS_CEILING = 50
MIN_ITERATIONS = 1


@app.before_request
def require_api_key():
    """SEC-002: Enforce API key authentication on /api/ routes."""
    if not request.path.startswith("/api/"):
        return
    # Health check doesn't need auth
    if request.path == "/api/health":
        return
    if not _ARO_API_KEY:
        return  # key not configured, skip enforcement (dev mode)
    provided = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided, _ARO_API_KEY):
        return jsonify({"error": "unauthorized"}), 401


# ─── Health Check (audit §4.5) ─────────────────────────────────────────
_start_time = time.time()


@app.route("/api/health")
def health_check():
    """Health endpoint for load balancer readiness/liveness probes."""
    uptime = time.time() - _start_time
    active_sessions = sum(
        1 for s in _session_status.values()
        if s.get("status") == "running"
    )
    return jsonify({
        "status": "ok",
        "version": "2.0.0",
        "active_sessions": active_sessions,
        "max_sessions": MAX_CONCURRENT_SESSIONS,
        "uptime_seconds": round(uptime, 1),
    })


@app.after_request
def add_security_headers(response):
    """SEC-007: Add HTTP security response headers."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if not response.headers.get("Content-Security-Policy"):
        response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


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
            vector_store_path=str(base_dir / config.vector_store_path),
            enable_cross_session_memory=config.enable_cross_session_memory,
        )
        gateway = ModelGateway(config=config, session_id=session_id, log_dir=logs_root)

        _session_status[session_id] = {"status": "running", "objective": objective}

        if mode == "fast":
            # Fast mode: single-pass async pipeline (15-30s target)
            import asyncio
            from runtime.event_bus import EventBus
            from agents.fast_orchestrator import FastOrchestrator

            event_bus = EventBus()
            fast_orch = FastOrchestrator(config, memory, gateway, event_bus)
            report = asyncio.run(fast_orch.run(objective))

            # Persist report to disk so /api/sessions and /api/report can find it
            fast_logger = SessionLogger(log_dir=logs_root, session_id=session_id, mode="fast")
            fast_logger.save_final_report(report)

            # Push completion to SSE queue
            report_data = report.model_dump() if hasattr(report, 'model_dump') else report.__dict__
            queue.put({"type": "complete", "report": report_data})
        else:
            # Standard mode: iterative multi-agent pipeline
            session_logger = SSESessionLogger(
                log_dir=logs_root,
                session_id=session_id,
                mode=config.mode,
                queue=queue,
            )
            orchestrator = Orchestrator(config, memory, gateway, session_logger)
            orchestrator._sse_queue = queue

            report = orchestrator.run(research_objective=objective, mode=mode)

        _session_status[session_id]["status"] = "complete"

    except Exception as exc:
        logger.exception("Research session %s failed: %s", session_id, exc)
        queue.put({"type": "error", "message": "An internal error occurred. Check server logs."})
        _session_status[session_id] = {
            "status": "error", "error": "internal error",
            "completed_at": time.time(),
        }
    finally:
        try:
            memory.close()
        except Exception:
            pass
        queue.put({"type": "done"})


# ─── API Endpoints ───────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def start_research():
    # SEC-006: Cap concurrent sessions to prevent DoS
    active = sum(
        1 for s in _session_status.values()
        if isinstance(s, dict) and s.get("status") == "running"
    )
    if active >= MAX_CONCURRENT_SESSIONS:
        return jsonify({"error": "too many concurrent sessions, try again later"}), 429

    data = request.get_json()  # SEC-016: removed force=True for CSRF protection
    if data is None:
        return jsonify({"error": "request body must be JSON with Content-Type: application/json"}), 415
    objective = data.get("objective", "").strip()
    if not objective:
        return jsonify({"error": "objective is required"}), 400

    mode = data.get("mode", "autonomous")
    runtime_mode = data.get("runtime_mode", "production")

    # SEC-011: Clamp max_iterations to safe range
    max_iterations = data.get("max_iterations", 10)
    try:
        max_iterations = int(max_iterations)
    except (TypeError, ValueError):
        max_iterations = 10
    max_iterations = max(MIN_ITERATIONS, min(max_iterations, MAX_ITERATIONS_CEILING))

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
    # SEC-003: Validate session_id format
    if not SESSION_ID_RE.match(session_id):
        return jsonify({"error": "invalid session id"}), 400

    queue = _progress_queues.get(session_id)
    if not queue:
        return jsonify({"error": "session not found"}), 404

    def generate():
        try:
            while True:
                try:
                    event = queue.get(timeout=300)
                except Exception:
                    yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            # SEC-013: Clean up queue after stream closes
            _progress_queues.pop(session_id, None)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/sessions")
def list_sessions():
    # SEC-013: Evict stale session state on each list call
    _evict_old_sessions()

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
    # SEC-003: Validate session_id format to prevent path traversal
    if not SESSION_ID_RE.match(session_id):
        return jsonify({"error": "invalid session id"}), 400

    base_dir = Path(__file__).resolve().parent
    logs_dir = base_dir / "logs"
    # Normalize session path and ensure it stays within logs_dir
    logs_dir_resolved = logs_dir.resolve()
    session_dir = (logs_dir_resolved / session_id).resolve()
    try:
        # Python 3.9+: use is_relative_to for a clear containment check
        is_within_logs = session_dir.is_relative_to(logs_dir_resolved)
    except AttributeError:
        # Fallback for older Python versions: explicitly walk parents
        is_within_logs = any(parent == logs_dir_resolved for parent in session_dir.parents)
    if not is_within_logs:
        return jsonify({"error": "invalid session id"}), 400

    report_file = session_dir / "final_report.json"

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


def _evict_old_sessions(max_age_seconds: int = 3600):
    """SEC-013: Remove stale session state to prevent memory leak."""
    cutoff = time.time() - max_age_seconds
    stale = [
        sid for sid, s in list(_session_status.items())
        if isinstance(s, dict)
        and s.get("status") not in ("running", "starting")
        and s.get("completed_at", float("inf")) < cutoff
    ]
    for sid in stale:
        _session_status.pop(sid, None)
        _progress_queues.pop(sid, None)


if __name__ == "__main__":
    # SEC-001: debug=False, bind to localhost only
    host = os.getenv("ARO_HOST", "127.0.0.1")
    port = int(os.getenv("ARO_PORT", "5000"))
    app.run(host=host, port=port, debug=False, threaded=True)
