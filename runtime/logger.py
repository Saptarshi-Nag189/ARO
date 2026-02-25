"""
Structured Logger
=================
JSON-structured logging for each iteration.
Stores logs in logs/{session_id}/iteration_X.json
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class IterationLog:
    """Accumulated log data for a single iteration."""

    def __init__(self, session_id: str, iteration: int):
        self.session_id = session_id
        self.iteration = iteration
        self.start_time = time.time()
        self.agent_logs: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}

    def log_agent_call(
        self,
        agent_name: str,
        inputs: Any,
        outputs: Any,
        token_usage: int = 0,
        execution_time: float = 0.0,
    ) -> None:
        """Log a single agent call within this iteration."""
        self.agent_logs.append({
            "agent": agent_name,
            "timestamp": datetime.utcnow().isoformat(),
            "inputs": self._safe_serialize(inputs),
            "outputs": self._safe_serialize(outputs),
            "token_usage": token_usage,
            "execution_time_seconds": round(execution_time, 3),
        })

    def set_metrics(
        self,
        hypothesis_confidence: float = 0.0,
        raw_confidence: float = 0.0,
        epistemic_risk: float = 1.0,
        risk_floor_applied: bool = False,
        novelty_score: float = 0.0,
        total_claims: int = 0,
        total_sources: int = 0,
        unresolved_gaps: int = 0,
        gap_count_before: int = 0,
        gap_count_after: int = 0,
        contradiction_cycle_count: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Set the iteration-level metrics."""
        self.metrics = {
            "hypothesis_confidence": round(hypothesis_confidence, 6),
            "raw_confidence": round(raw_confidence, 6),
            "epistemic_risk": round(epistemic_risk, 6),
            "risk_floor_applied": risk_floor_applied,
            "novelty_score": round(novelty_score, 6),
            "total_claims": total_claims,
            "total_sources": total_sources,
            "unresolved_gaps": unresolved_gaps,
            "gap_count_before": gap_count_before,
            "gap_count_after": gap_count_after,
            "contradiction_cycle_count": contradiction_cycle_count,
            "total_tokens_this_iteration": total_tokens,
            "total_execution_time_seconds": round(
                time.time() - self.start_time, 3
            ),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "session_id": self.session_id,
            "iteration": self.iteration,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_logs": self.agent_logs,
            "metrics": self.metrics,
        }

    @staticmethod
    def _safe_serialize(obj: Any) -> Any:
        """Safely serialize an object to JSON-compatible form."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, dict):
            return {k: IterationLog._safe_serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [IterationLog._safe_serialize(item) for item in obj]
        return str(obj)


class SessionLogger:
    """Manages structured JSON logging for a research session."""

    def __init__(self, log_dir: str, session_id: str, mode: str = "production"):
        self.session_dir = os.path.join(log_dir, session_id)
        self.session_id = session_id
        os.makedirs(self.session_dir, exist_ok=True)

        self.mode = mode

        if self.mode == "audit":
            self.reasoning_dir = os.path.join(self.session_dir, "reasoning_traces")
            os.makedirs(self.reasoning_dir, exist_ok=True)

        # Also set up Python logging
        self._setup_python_logger()

    def _setup_python_logger(self) -> None:
        """Configure Python's logging for the session."""
        log_file = os.path.join(self.session_dir, "session.log")
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        ))
        root_logger = logging.getLogger("aro")
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)

    def create_iteration_log(self, iteration: int) -> IterationLog:
        """Create a new iteration log."""
        return IterationLog(self.session_id, iteration)

    def save_iteration_log(self, log: IterationLog) -> str:
        """Save an iteration log to disk."""
        filename = f"iteration_{log.iteration}.json"
        filepath = os.path.join(self.session_dir, filename)

        with open(filepath, "w") as f:
            json.dump(log.to_dict(), f, indent=2, default=str)

        logging.getLogger("aro.logger").info(
            "Saved iteration %d log to %s", log.iteration, filepath
        )
        return filepath

    def save_final_report(self, report: Any) -> str:
        """Save the final report to disk."""
        filepath = os.path.join(self.session_dir, "final_report.json")

        data = report.model_dump() if hasattr(report, "model_dump") else report
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logging.getLogger("aro.logger").info(
            "Saved final report to %s", filepath
        )
        return filepath
