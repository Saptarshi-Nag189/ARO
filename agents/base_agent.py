"""
Base Agent
==========
Abstract base class for all ARO agents.

Since the LangGraph migration (v3), an agent is a pure SPECIFICATION:
a name, a system prompt, and a strict Pydantic output schema. Execution
lives in the graph (graph/nodes.py + graph/structured.py), which
invokes the agent's prompt/schema through a LangChain chat model.

Rules enforced:
- All agents return structured JSON only (validated by the graph layer)
- All agents follow strict Pydantic schemas
- No agent accesses the database directly
- No agent controls loop execution
- No agent modifies global state
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger("aro.agents")


class BaseAgent(ABC):
    """Abstract agent specification: name + system prompt + output schema."""

    def __init__(self, name: str, gateway: Optional[Any] = None):
        # `gateway` is accepted (and ignored) for backwards compatibility
        # with v2 call sites; execution is owned by the graph layer now.
        self.name = name
        self.logger = logging.getLogger(f"aro.agents.{name}")

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    @abstractmethod
    def get_output_schema(self) -> Type[BaseModel]:
        """Return the Pydantic schema class for this agent's output."""
