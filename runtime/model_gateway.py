"""
Model Gateway
=============
Wraps the OpenRouter API for model-agnostic access.
- Configurable model per agent
- Enforces JSON-only output
- Validates output against Pydantic schema
- Retry on malformed output (max 3 attempts)
- Logs raw and validated outputs
- Supports temperature configuration per agent
- Tracks token usage per call

All agents must use this gateway. No direct API calls allowed.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from config import AROConfig, ModelConfig

logger = logging.getLogger("aro.model_gateway")

T = TypeVar("T", bound=BaseModel)


class ModelGatewayError(Exception):
    """Raised when the model gateway fails after all retries."""
    pass


class ModelGateway:
    """
    OpenRouter API wrapper with schema validation and retry logic.
    Uses direct HTTP requests to https://openrouter.ai/api/v1/chat/completions
    """

    def __init__(
        self,
        config: AROConfig,
        session_id: Optional[str] = None,
        log_dir: Optional[str] = None,
    ):
        self.config = config
        self.base_url = config.openrouter_base_url
        self.api_key = config.openrouter_api_key
        self.max_retries = config.max_retries
        self._total_tokens_used = 0

        self.session_id = session_id
        self.log_dir = log_dir or config.log_dir
        if getattr(self.config, "mode", "production") == "audit" and session_id:
            self.reasoning_dir = os.path.join(
                self.log_dir, session_id, "reasoning_traces"
            )
            os.makedirs(self.reasoning_dir, exist_ok=True)
        else:
            self.reasoning_dir = None

        # Async client with connection pooling (per audit §4.3.5)
        self._async_client = None  # Lazy-initialized

    def _get_async_client(self):
        """Lazy-init httpx.AsyncClient with connection pooling."""
        if self._async_client is None:
            try:
                import httpx
                self._async_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(120.0),
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                    ),
                )
            except ImportError:
                raise ImportError(
                    "httpx is required for async operations. "
                    "Install it with: pip install httpx"
                )
        return self._async_client

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens_used

    async def call_async(
        self,
        agent_name: str,
        messages: List[Dict[str, str]],
        response_schema: Type[T],
        system_prompt: Optional[str] = None,
        extra_context: Optional[str] = None,
    ) -> T:
        """
        Async version of call(). Same retry + validation logic,
        but uses httpx.AsyncClient for non-blocking I/O.

        ~30% faster per call due to TCP connection reuse.
        Enables asyncio.gather() for parallel agent execution.
        """
        model_config = self.config.get_model_config(agent_name)
        client = self._get_async_client()

        # Build messages (same logic as sync call)
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        schema_instruction = (
            f"\n\nYou MUST respond with ONLY valid JSON that conforms to this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Do not include any text outside of the JSON object. "
            f"Do not wrap the JSON in markdown code fences. "
            f"Output ONLY the raw JSON object."
        )

        if full_messages and full_messages[-1]["role"] == "user":
            full_messages[-1]["content"] += schema_instruction
        else:
            full_messages.append({"role": "user", "content": schema_instruction})

        last_error = None
        raw_output = None

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_output, token_usage, reasoning_details = await self._make_request_async(
                    client, model_config, full_messages
                )
                self._total_tokens_used += token_usage

                logger.debug(
                    "Gateway async raw output [%s] attempt %d: %s",
                    agent_name, attempt, raw_output[:500]
                )

                validated = self._parse_and_validate(raw_output, response_schema)

                logger.info(
                    "Gateway async validated [%s] attempt %d: success (tokens: %d)",
                    agent_name, attempt, token_usage,
                )
                return validated

            except (json.JSONDecodeError, ValidationError, KeyError) as e:
                last_error = e
                logger.warning(
                    "Gateway async validation failed [%s] attempt %d/%d: %s",
                    agent_name, attempt, self.max_retries, str(e)[:200],
                )
                if attempt < self.max_retries:
                    correction = (
                        f"Your previous response was not valid JSON or did not match "
                        f"the required schema. Error: {str(e)[:300]}. "
                        f"Please try again. Output ONLY the raw JSON object."
                    )
                    full_messages.append({"role": "assistant", "content": raw_output or ""})
                    full_messages.append({"role": "user", "content": correction})

            except Exception as e:
                last_error = e
                logger.error(
                    "Gateway async request failed [%s] attempt %d/%d: %s",
                    agent_name, attempt, self.max_retries, str(e),
                )
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise ModelGatewayError(
            f"All {self.max_retries} async attempts failed for '{agent_name}'. "
            f"Last error: {last_error}. Last raw: {(raw_output or '')[:300]}"
        )

    async def _make_request_async(
        self,
        client,
        model_config: ModelConfig,
        messages: List[Dict[str, Any]],
    ) -> tuple:
        """Async HTTP request to OpenRouter via httpx."""
        # Per-model API key routing
        api_key = self.config.get_api_key_for_model(model_config.model_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_config.model_id,
            "messages": messages,
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
            "response_format": {"type": "json_object"},
        }

        # Reasoning: enabled per-agent (Step 3.5 Flash, GPT-OSS-120B)
        # or globally in audit mode
        enable_reasoning = (
            getattr(model_config, "enable_reasoning", False)
            or getattr(self.config, "mode", "production") == "audit"
        )
        if enable_reasoning:
            payload["reasoning"] = {"enabled": True}
        else:
            payload["provider"] = {
                "require_parameters": True,
                "allow_fallbacks": False,
            }

        response = await client.post(
            self.base_url,
            headers=headers,
            content=json.dumps(payload),
        )
        response.raise_for_status()

        result = response.json()
        message = result["choices"][0]["message"]
        content = message["content"]
        reasoning_details = message.get("reasoning_details") or result.get("reasoning_details")

        # Hard guard: only block reasoning leaks from non-reasoning models in prod
        if (
            getattr(self.config, "mode", "production") == "production"
            and reasoning_details
            and not getattr(model_config, "enable_reasoning", False)
        ):
            raise ModelGatewayError(
                "HARD GUARD VIOLATION: Reasoning details detected from non-reasoning model in production."
            )

        usage = result.get("usage", {})
        token_usage = usage.get("total_tokens", 0)
        return content, token_usage, reasoning_details

    async def close_async(self):
        """Close the async client and release connections."""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def call(
        self,
        agent_name: str,
        messages: List[Dict[str, str]],
        response_schema: Type[T],
        system_prompt: Optional[str] = None,
        extra_context: Optional[str] = None,
    ) -> T:
        """
        Make a model call with schema validation and retry.

        Args:
            agent_name: Name of the calling agent (for model selection).
            messages: Conversation messages.
            response_schema: Pydantic model class to validate output against.
            system_prompt: Optional system-level instruction.
            extra_context: Additional context to append to user message.

        Returns:
            Validated Pydantic model instance.

        Raises:
            ModelGatewayError: If all retries fail.
        """
        model_config = self.config.get_model_config(agent_name)

        # Build message list
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Add schema instruction to guide the model
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        schema_instruction = (
            f"\n\nYou MUST respond with ONLY valid JSON that conforms to this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Do not include any text outside of the JSON object. "
            f"Do not wrap the JSON in markdown code fences. "
            f"Output ONLY the raw JSON object."
        )

        # Append schema instruction to the last user message
        if full_messages and full_messages[-1]["role"] == "user":
            full_messages[-1]["content"] += schema_instruction
        else:
            full_messages.append({"role": "user", "content": schema_instruction})

        last_error = None
        raw_output = None

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_output, token_usage, reasoning_details = self._make_request(
                    model_config, full_messages
                )

                self._total_tokens_used += token_usage

                if getattr(self.config, "mode", "production") == "audit":
                    # Persist every audit-mode call so reasoning instrumentation
                    # is verifiable even when provider omits reasoning_details.
                    persisted_reasoning = reasoning_details
                    if persisted_reasoning is None:
                        persisted_reasoning = {
                            "reasoning_details_missing": True
                        }
                    self._persist_reasoning_trace(
                        agent_name=agent_name,
                        attempt=attempt,
                        model_id=model_config.model_id,
                        reasoning_details=persisted_reasoning,
                    )

                # Log raw output
                logger.debug(
                    "Gateway raw output [%s] attempt %d: %s",
                    agent_name, attempt, raw_output[:500]
                )

                # Parse and validate
                validated = self._parse_and_validate(raw_output, response_schema)

                logger.info(
                    "Gateway validated output [%s] attempt %d: success "
                    "(tokens: %d)",
                    agent_name, attempt, token_usage,
                )

                return validated

            except (json.JSONDecodeError, ValidationError, KeyError) as e:
                last_error = e
                logger.warning(
                    "Gateway validation failed [%s] attempt %d/%d: %s",
                    agent_name, attempt, self.max_retries, str(e)[:200],
                )

                # On retry, add a correction message
                if attempt < self.max_retries:
                    correction = (
                        f"Your previous response was not valid JSON or did not match "
                        f"the required schema. Error: {str(e)[:300]}. "
                        f"Please try again. Output ONLY the raw JSON object, "
                        f"no markdown fences, no extra text."
                    )
                    assistant_msg = {"role": "assistant", "content": raw_output or ""}
                    # Only append reasoning to assistant message on retry if audit mode
                    if (
                        self.config.mode == "audit"
                        and reasoning_details is not None
                    ):
                        assistant_msg["reasoning_details"] = reasoning_details
                    full_messages.append(assistant_msg)
                    full_messages.append({"role": "user", "content": correction})

            except requests.RequestException as e:
                last_error = e
                logger.error(
                    "Gateway request failed [%s] attempt %d/%d: %s",
                    agent_name, attempt, self.max_retries, str(e),
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff for network errors

        raise ModelGatewayError(
            f"All {self.max_retries} attempts failed for agent '{agent_name}'. "
            f"Last error: {last_error}. Last raw output: {(raw_output or '')[:300]}"
        )

    def _make_request(
        self,
        model_config: ModelConfig,
        messages: List[Dict[str, Any]],
    ) -> tuple:
        """Make the actual HTTP request to OpenRouter."""
        # Per-model API key routing
        api_key = self.config.get_api_key_for_model(model_config.model_id)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_config.model_id,
            "messages": messages,
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
            "response_format": {"type": "json_object"},
        }

        # Reasoning: enabled per-agent (Step 3.5 Flash, GPT-OSS-120B)
        # or globally in audit mode
        enable_reasoning = (
            getattr(model_config, "enable_reasoning", False)
            or getattr(self.config, "mode", "production") == "audit"
        )

        if enable_reasoning:
            payload["reasoning"] = {"enabled": True}
        else:
            payload["provider"] = {
                "require_parameters": True,
                "allow_fallbacks": False,
            }

        response = requests.post(
            self.base_url,
            headers=headers,
            data=json.dumps(payload),
            timeout=120,
        )
        response.raise_for_status()

        result = response.json()

        # Extract content and token usage
        message = result["choices"][0]["message"]
        content = message["content"]
        
        reasoning_details = message.get("reasoning_details")
        if reasoning_details is None:
            reasoning_details = result.get("reasoning_details")

        # Hard guard: only block reasoning leaks from non-reasoning models in prod
        if (
            getattr(self.config, "mode", "production") == "production"
            and reasoning_details
            and not getattr(model_config, "enable_reasoning", False)
        ):
            raise ModelGatewayError(
                "HARD GUARD VIOLATION: Reasoning details detected from non-reasoning model in production."
            )

        usage = result.get("usage", {})
        token_usage = usage.get("total_tokens", 0)

        return content, token_usage, reasoning_details

    def _persist_reasoning_trace(
        self,
        agent_name: str,
        attempt: int,
        model_id: str,
        reasoning_details: Any,
    ) -> None:
        """Persist audit-mode reasoning traces outside structured memory."""
        if not self.reasoning_dir:
            return

        trace_data = {
            "session_id": self.session_id,
            "agent_name": agent_name,
            "attempt": attempt,
            "model": model_id,
            "timestamp": datetime.utcnow().isoformat(),
            "reasoning_details": reasoning_details,
        }
        trace_filename = (
            f"{agent_name}_{attempt}_{int(time.time() * 1000)}.json"
        )
        trace_filepath = os.path.join(self.reasoning_dir, trace_filename)
        with open(trace_filepath, "w") as trace_file:
            json.dump(trace_data, trace_file, indent=2, default=str)

    def _parse_and_validate(
        self, raw_output: str, schema: Type[T]
    ) -> T:
        """Parse raw JSON string and validate against Pydantic schema."""
        # Strip markdown code fences if present
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last line (fences)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)
