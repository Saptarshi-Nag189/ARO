"""
Graph Services
==============
Non-serializable runtime dependencies for the graph nodes. These are
closed over when the graph is built (one graph per session), keeping
the checkpointed state purely data.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from langchain_core.language_models.chat_models import BaseChatModel

from config import AROConfig
from graph.models import get_chat_model, get_plain_chat_model
from memory.memory_service import MemoryService
from runtime.logger import SessionLogger


def _noop_emit(event_type: str, data: dict) -> None:
    return None


@dataclass
class GraphServices:
    """Everything a node needs beyond the checkpointed state."""

    config: AROConfig
    memory: MemoryService
    session_logger: Optional[SessionLogger] = None
    # emit(event_type, data): wired to the SSE queue by the web app,
    # to logging by the CLI. Nodes emit agent_start / agent_done /
    # iteration_complete / phase_* / complete events through this.
    emit: Callable[[str, dict], None] = field(default=_noop_emit)

    def model_for(self, agent_name: str) -> BaseChatModel:
        return get_chat_model(agent_name, self.config)

    def plain_model_for(self, agent_name: str) -> BaseChatModel:
        return get_plain_chat_model(agent_name, self.config)

    def safe_emit(self, event_type: str, data: Optional[dict] = None) -> None:
        try:
            self.emit(event_type, data or {})
        except Exception:  # never let a listener kill the pipeline
            pass
