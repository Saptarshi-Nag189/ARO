"""
Chat Model Factory
==================
LangChain chat-model construction for every agent, preserving the
per-agent model/temperature routing from AROConfig.agent_models.

Providers (selected via ARO_MODEL_PROVIDER):
- "openrouter" (default): ChatOpenAI against OpenRouter's
  OpenAI-compatible endpoint, with per-model API-key routing and the
  same reasoning flag the old ModelGateway sent.
- "bedrock": ChatBedrockConverse (requires `pip install langchain-aws`
  and AWS credentials). Used in the AWS deployment.
- ARO_FAKE_MODEL=1 overrides everything with a deterministic offline
  fake — this is what CI and the test suite run on.
"""

import json
import os
import re
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from config import AROConfig


def use_fake_model() -> bool:
    return os.getenv("ARO_FAKE_MODEL", "").strip() in ("1", "true", "yes")


def get_chat_model(agent_name: str, config: AROConfig) -> BaseChatModel:
    """Return the chat model configured for this agent."""
    if use_fake_model():
        return FakeAgentModel(agent_name=agent_name)

    provider = os.getenv("ARO_MODEL_PROVIDER", "openrouter").lower()
    model_config = config.get_model_config(agent_name)

    if provider == "bedrock":
        try:
            from langchain_aws import ChatBedrockConverse
        except ImportError as exc:
            raise ImportError(
                "ARO_MODEL_PROVIDER=bedrock requires langchain-aws. "
                "Install it with: pip install langchain-aws"
            ) from exc
        return ChatBedrockConverse(
            model=os.getenv(
                "ARO_BEDROCK_MODEL",
                "anthropic.claude-3-5-sonnet-20241022-v2:0",
            ),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        )

    # Default: OpenRouter via the OpenAI-compatible API
    from langchain_openai import ChatOpenAI

    base_url = config.openrouter_base_url
    # Config historically stores the full chat/completions URL; ChatOpenAI
    # wants the API base.
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]

    extra_body = {}
    if getattr(model_config, "enable_reasoning", False) or config.mode == "audit":
        extra_body["reasoning"] = {"enabled": True}
    else:
        extra_body["provider"] = {
            "require_parameters": True,
            "allow_fallbacks": False,
        }

    return ChatOpenAI(
        model=model_config.model_id,
        api_key=config.get_api_key_for_model(model_config.model_id),
        base_url=base_url,
        temperature=model_config.temperature,
        max_tokens=model_config.max_tokens,
        timeout=120,
        max_retries=2,
        model_kwargs={"response_format": {"type": "json_object"}},
        extra_body=extra_body or None,
    )


def get_plain_chat_model(agent_name: str, config: AROConfig) -> BaseChatModel:
    """Chat model for free-text (non-JSON) calls, e.g. report conclusions."""
    if use_fake_model():
        return FakeAgentModel(agent_name=agent_name)

    model = get_chat_model(agent_name, config)
    # Drop the JSON response_format for plain-text generation.
    if hasattr(model, "model_kwargs"):
        kwargs = dict(model.model_kwargs or {})
        kwargs.pop("response_format", None)
        model.model_kwargs = kwargs
    return model


# ─── Deterministic offline fake ──────────────────────────────────────────


def _fake_payload(agent_name: str, prompt: str = "") -> Any:
    """Schema-valid canned output per agent, for offline runs and CI.

    Prompt-aware where the guardrails demand it: claim extraction reuses
    the real registered source IDs listed in the prompt, and synthesis
    references real claim IDs — the persistence guardrails DROP anything
    with unknown IDs (never reattribute), so a naive fake would produce
    empty runs.
    """
    if agent_name == "claim_extraction":
        source_ids = re.findall(r"^\s{2}(src_[A-Za-z0-9_]+): ", prompt, flags=re.M)
        src_a = source_ids[0] if source_ids else "src_1"
        src_b = source_ids[1] if len(source_ids) > 1 else src_a
        return {
            "claims": [
                {"subject": "The field", "relation": "advanced_in", "object": "2024",
                 "source_id": src_a, "confidence_estimate": 0.8,
                 "credibility_weight": 0.85},
                {"subject": "Evaluation methods", "relation": "remain",
                 "object": "an open challenge",
                 "source_id": src_b, "confidence_estimate": 0.7,
                 "credibility_weight": 0.75},
            ],
            "extraction_notes": None,
        }

    if agent_name == "synthesis":
        claim_ids = re.findall(r"\[(claim_[a-f0-9]+)\]", prompt)
        supporting = claim_ids[:1] if claim_ids else ["c1"]
        return {
            "hypotheses": [
                {"statement": "Recent advances outpace evaluation methodology.",
                 "supporting_claim_ids": supporting, "opposing_claim_ids": [],
                 "confidence": 0.6, "status": "proposed"}
            ],
            "merged_claims": [],
            "narrative_summary": "Evidence suggests rapid progress with lagging evaluation.",
            "relationships": [],
            "resolved_contradictions": [],
            "resolved_gap_ids": [],
        }

    payloads = {
        "planner": {
            "research_objective_summary": "Fake restated objective.",
            "sub_questions": [
                {"question": "What is the state of the art?",
                 "priority": 1, "search_strategy": "academic"},
                {"question": "What are the open challenges?",
                 "priority": 2, "search_strategy": "general"},
            ],
            "iteration_targets": ["Survey the landscape"],
            "recommended_sources": ["arxiv"],
        },
        "research": {
            "findings": [
                {"content": "Finding A: the field advanced significantly in 2024.",
                 "source_title": "Fake Journal of AI",
                 "source_url": "https://example.org/paper-a",
                 "credibility_estimate": 0.85, "relevance": 0.9},
                {"content": "Finding B: open challenges remain in evaluation.",
                 "source_title": "Fake Conference Proceedings",
                 "source_url": "https://example.org/paper-b",
                 "credibility_estimate": 0.75, "relevance": 0.8},
            ],
            "sources_consulted": 2,
            "search_queries_used": ["state of the art", "open challenges"],
        },
        "skeptic": {
            "contradictions": [],
            "credibility_challenges": [],
            "knowledge_gaps": [
                {"description": "No longitudinal data on evaluation robustness.",
                 "severity": 0.4}
            ],
            "overall_assessment": "Claims are plausible but thinly sourced.",
        },
        "innovation": {
            "proposals": [
                {"title": "Adaptive evaluation harness",
                 "description": "An evaluation harness that adapts to model capability.",
                 "differentiation": "Prior art evaluates statically.",
                 "prior_art_references": ["https://example.org/prior"],
                 "estimated_novelty": 0.7,
                 "addressed_gaps": []}
            ],
            "prior_art_summary": "Static benchmarks dominate prior art.",
            "overall_novelty_assessment": "Moderately novel direction.",
        },
        "reflection": {
            "meta_analysis": "Research is progressing steadily.",
            "confidence_trend": "stable",
            "gap_assessment": "One structural gap remains open.",
            "strategy_adjustments": [],
            "epistemic_risk": 0.4,
            "advisory_should_stop": False,
            "advisory_reason": "Coverage is adequate; deterministic checks decide.",
        },
        "fast_synthesis": {
            "research_objective": "Fake objective",
            "executive_summary": "A comprehensive fake summary of the research topic "
                                 "covering the main findings in enough detail to be useful.",
            "key_findings": ["Finding one.", "Finding two.", "Finding three."],
            "conclusion": "The evidence supports a clear, direct fake conclusion.",
            "confidence_score": 0.72,
            "knowledge_gaps": ["Longitudinal data is missing."],
        },
    }
    return payloads.get(agent_name)


class FakeAgentModel(BaseChatModel):
    """Deterministic offline chat model. One instance per agent.

    Returns schema-valid JSON for structured agents and plain prose for
    free-text calls (conclusion). Reports constant token usage so token
    accounting is exactly testable.
    """

    agent_name: str = "default"

    @property
    def _llm_type(self) -> str:
        return "aro-fake"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = ""
        for message in messages:
            if isinstance(message.content, str):
                prompt += message.content + "\n"
        payload = _fake_payload(self.agent_name, prompt)
        if payload is None:
            text = (
                "Based on the available evidence, the fake conclusion is that "
                "the research question is answered affirmatively with moderate "
                "confidence. Key caveat: this is deterministic offline output."
            )
        else:
            text = json.dumps(payload)
        message = AIMessage(
            content=text,
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])
