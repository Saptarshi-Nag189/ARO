"""
Structured Invocation
=====================
Schema-validated LLM invocation with the same resilience the old
ModelGateway had: schema instruction injected into the prompt, JSON
parsed and validated against the agent's Pydantic schema, and a
correction round-trip on malformed output. Free OpenRouter models do
not reliably support native tool calling, so prompt-enforced JSON with
retry remains the robust choice; the logic is expressed over LangChain
messages so every attempt is traced in LangSmith.
"""

import json
import logging
from typing import List, Tuple, Type, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("aro.graph.structured")

T = TypeVar("T", bound=BaseModel)


class StructuredInvocationError(Exception):
    """Raised when all attempts to get schema-valid output fail."""


def _schema_instruction(schema: Type[BaseModel]) -> str:
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    return (
        f"\n\nYou MUST respond with ONLY valid JSON that conforms to this schema:\n"
        f"```json\n{schema_json}\n```\n"
        f"Do not include any text outside of the JSON object. "
        f"Do not wrap the JSON in markdown code fences. "
        f"Output ONLY the raw JSON object."
    )


def parse_and_validate(raw_output: str, schema: Type[T]) -> T:
    """Parse raw model output into a validated schema instance."""
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    parsed = json.loads(cleaned)
    return schema.model_validate(parsed)


def _usage_tokens(message: AIMessage) -> int:
    usage = getattr(message, "usage_metadata", None) or {}
    return int(usage.get("total_tokens", 0))


def invoke_structured(
    model: BaseChatModel,
    agent_name: str,
    system_prompt: str,
    user_message: str,
    schema: Type[T],
    max_retries: int = 3,
) -> Tuple[T, int]:
    """Invoke a chat model and validate output against `schema`.

    Returns (validated_output, total_tokens_used_across_attempts).
    """
    messages: List[BaseMessage] = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_message + _schema_instruction(schema)))

    tokens_used = 0
    last_error = None
    raw_output = None

    for attempt in range(1, max_retries + 1):
        try:
            response = model.invoke(messages)
            raw_output = response.content if isinstance(response.content, str) else str(response.content)
            tokens_used += _usage_tokens(response)

            validated = parse_and_validate(raw_output, schema)
            logger.info(
                "Structured output [%s] attempt %d: valid (tokens so far: %d)",
                agent_name, attempt, tokens_used,
            )
            return validated, tokens_used

        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            last_error = exc
            logger.warning(
                "Structured output [%s] attempt %d/%d invalid: %s",
                agent_name, attempt, max_retries, str(exc)[:200],
            )
            if attempt < max_retries:
                messages.append(AIMessage(content=raw_output or ""))
                messages.append(HumanMessage(content=(
                    f"Your previous response was not valid JSON or did not match "
                    f"the required schema. Error: {str(exc)[:300]}. "
                    f"Please try again. Output ONLY the raw JSON object, "
                    f"no markdown fences, no extra text."
                )))

        except Exception as exc:  # network / provider errors
            last_error = exc
            logger.error(
                "Model call failed [%s] attempt %d/%d: %s",
                agent_name, attempt, max_retries, exc,
            )
            if attempt < max_retries:
                import time
                time.sleep(2 ** attempt)

    raise StructuredInvocationError(
        f"All {max_retries} attempts failed for agent '{agent_name}'. "
        f"Last error: {last_error}. Last raw output: {(raw_output or '')[:300]}"
    )


def invoke_plain(
    model: BaseChatModel,
    user_message: str,
    system_prompt: str = "",
) -> Tuple[str, int]:
    """Single free-text invocation (used for the report conclusion)."""
    messages: List[BaseMessage] = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_message))
    response = model.invoke(messages)
    content = response.content if isinstance(response.content, str) else str(response.content)
    return content.strip(), _usage_tokens(response)
