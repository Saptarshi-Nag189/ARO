"""Structured invocation: parsing, validation, and the correction retry loop."""

import json
from typing import Any, List, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel

from graph.structured import (
    StructuredInvocationError,
    invoke_structured,
    parse_and_validate,
)


class _Answer(BaseModel):
    value: int
    label: str


class ScriptedModel(BaseChatModel):
    """Returns a scripted sequence of responses, one per invocation."""

    responses: List[str]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self.responses[min(self.calls, len(self.responses) - 1)]
        # object.__setattr__ because pydantic models are frozen-ish here
        object.__setattr__(self, "calls", self.calls + 1)
        message = AIMessage(
            content=text,
            usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_parse_strips_markdown_fences():
    raw = '```json\n{"value": 7, "label": "ok"}\n```'
    parsed = parse_and_validate(raw, _Answer)
    assert parsed.value == 7 and parsed.label == "ok"


def test_valid_first_attempt():
    model = ScriptedModel(responses=[json.dumps({"value": 1, "label": "a"})])
    out, tokens = invoke_structured(model, "test", "sys", "user", _Answer)
    assert out.value == 1
    assert tokens == 10
    assert model.calls == 1


def test_correction_retry_recovers_from_bad_json():
    model = ScriptedModel(responses=[
        "this is not json at all",
        json.dumps({"value": 2, "label": "recovered"}),
    ])
    out, tokens = invoke_structured(model, "test", "sys", "user", _Answer)
    assert out.label == "recovered"
    assert model.calls == 2
    assert tokens == 20, "tokens from failed attempts must still be counted"


def test_all_retries_exhausted_raises():
    model = ScriptedModel(responses=["nope"])
    with pytest.raises(StructuredInvocationError):
        invoke_structured(model, "test", "sys", "user", _Answer, max_retries=2)
    assert model.calls == 2
