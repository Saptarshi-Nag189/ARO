"""ModelGateway parsing, retry-with-correction, and call_text routing."""

import json
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from config import AROConfig
from runtime.model_gateway import ModelGateway, ModelGatewayError


class Echo(BaseModel):
    value: str


@pytest.fixture
def gateway():
    cfg = AROConfig()
    cfg.openrouter_api_key = "default-key"
    cfg.openrouter_api_key_gpt_oss = "gptoss-key"
    return ModelGateway(cfg)


# ─── _parse_and_validate ─────────────────────────────────────────────────


def test_parse_plain_json(gateway):
    assert gateway._parse_and_validate('{"value": "x"}', Echo).value == "x"


def test_parse_strips_markdown_fences(gateway):
    raw = '```json\n{"value": "x"}\n```'
    assert gateway._parse_and_validate(raw, Echo).value == "x"


def test_parse_rejects_schema_mismatch(gateway):
    with pytest.raises(Exception):
        gateway._parse_and_validate('{"wrong": 1}', Echo)


def test_parse_rejects_non_json(gateway):
    with pytest.raises(json.JSONDecodeError):
        gateway._parse_and_validate("not json at all", Echo)


# ─── call(): retry-with-correction ───────────────────────────────────────


def test_call_retries_on_invalid_json_then_succeeds(gateway):
    responses = iter([
        ("garbage", 10, None),
        ('{"value": "ok"}', 10, None),
    ])
    with patch.object(gateway, "_make_request", side_effect=lambda *a: next(responses)):
        result = gateway.call("synthesis", [{"role": "user", "content": "hi"}], Echo)
    assert result.value == "ok"
    assert gateway.total_tokens_used == 20


def test_call_raises_after_exhausting_retries(gateway):
    with patch.object(gateway, "_make_request", return_value=("garbage", 1, None)):
        with pytest.raises(ModelGatewayError):
            gateway.call("synthesis", [{"role": "user", "content": "hi"}], Echo)


# ─── call_text(): key routing + token accounting (finding 2.10) ──────────


class _FakeResp:
    def __init__(self, content=" hello "):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"total_tokens": 42},
        }


def test_call_text_routes_per_model_key_and_counts_tokens(gateway):
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["auth"] = headers["Authorization"]
        return _FakeResp()

    with patch("runtime.model_gateway.requests.post", fake_post):
        out = gateway.call_text("synthesis", [{"role": "user", "content": "hi"}])

    assert out == "hello"
    # synthesis runs on GPT-OSS, which has a dedicated key configured
    assert captured["auth"] == "Bearer gptoss-key"
    assert gateway.total_tokens_used == 42


def test_call_text_falls_back_to_default_key(gateway):
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["auth"] = headers["Authorization"]
        return _FakeResp()

    with patch("runtime.model_gateway.requests.post", fake_post):
        gateway.call_text("research", [{"role": "user", "content": "hi"}])

    # research runs on Trinity → default key
    assert captured["auth"] == "Bearer default-key"
