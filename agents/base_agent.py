"""
Base Agent
==========
Abstract base class for all ARO agents.
Enforces model-agnostic, schema-validated, JSON-only communication.
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from runtime.model_gateway import ModelGateway

logger = logging.getLogger("aro.agents")

T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC):
    """
    Abstract base class for all ARO agents.

    Rules enforced:
    - All agents use ModelGateway (no direct API calls)
    - All agents return structured JSON only
    - All agents follow strict Pydantic schemas
    - No agent accesses the database directly
    - No agent controls loop execution
    - No agent modifies global state
    """

    def __init__(self, name: str, gateway: ModelGateway):
        self.name = name
        self.gateway = gateway
        self.logger = logging.getLogger(f"aro.agents.{name}")

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

    @abstractmethod
    def get_output_schema(self) -> Type[BaseModel]:
        """Return the Pydantic schema class for this agent's output."""
        pass

    def run(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> BaseModel:
        """
        Execute this agent with the given input.

        Args:
            user_message: The main input/prompt for this agent.
            context: Optional additional context dictionary.

        Returns:
            Validated Pydantic model instance.
        """
        start_time = time.time()

        messages = self._build_messages(user_message, context)

        self.logger.info("Agent '%s' starting execution", self.name)

        result = self.gateway.call(
            agent_name=self.name,
            messages=messages,
            response_schema=self.get_output_schema(),
            system_prompt=self.get_system_prompt(),
        )

        elapsed = time.time() - start_time
        self.logger.info(
            "Agent '%s' completed in %.2fs", self.name, elapsed
        )

        return result

    def _build_messages(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Build the message list for the model call."""
        content = user_message
        if context:
            context_str = "\n\nAdditional Context:\n"
            for key, value in context.items():
                if isinstance(value, BaseModel):
                    context_str += f"\n{key}:\n{value.model_dump_json(indent=2)}\n"
                elif isinstance(value, list):
                    items_str = "\n".join(
                        item.model_dump_json(indent=2) if hasattr(item, "model_dump_json") else str(item)
                        for item in value
                    )
                    context_str += f"\n{key}:\n{items_str}\n"
                else:
                    context_str += f"\n{key}: {value}\n"
            content += context_str

        return [{"role": "user", "content": content}]
