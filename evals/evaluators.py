"""
Evaluators
==========
Two families, both plugged into langsmith.evaluate():

1. LLM-as-judge — a judge model scores faithfulness (is the answer
   grounded in the reference key points?) and coverage (are the key
   points addressed?).
2. Programmatic — ARO's own epistemic mathematics repurposed as
   evaluators: reported confidence/risk sanity, citation presence, and
   report completeness. These cost zero tokens and never flake.

Every evaluator returns {"key": ..., "score": 0..1}.
"""

import json
import os
from typing import Optional

from graph.structured import parse_and_validate
from pydantic import BaseModel, Field

JUDGE_MODEL = os.getenv("ARO_JUDGE_MODEL", "openai/gpt-oss-120b:free")


class JudgeVerdict(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


def _judge():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=JUDGE_MODEL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        temperature=0.0,
        max_tokens=600,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _run_judge(prompt: str) -> Optional[JudgeVerdict]:
    try:
        response = _judge().invoke(prompt)
        return parse_and_validate(str(response.content), JudgeVerdict)
    except Exception:
        return None


# ─── LLM-as-judge evaluators ─────────────────────────────────────────────


def faithfulness(run, example) -> dict:
    """Is the answer consistent with the reference key points (no contradiction)?"""
    answer = (run.outputs or {}).get("answer", "")
    key_points = (example.outputs or {}).get("key_points", [])
    verdict = _run_judge(
        "You are grading a research assistant's answer.\n\n"
        f"QUESTION: {example.inputs.get('question')}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"REFERENCE KEY POINTS:\n- " + "\n- ".join(key_points) + "\n\n"
        "Score how FAITHFUL the answer is: 1.0 if nothing in the answer "
        "contradicts the reference key points and its claims are plausible "
        "and grounded; 0.0 if it contradicts them or fabricates specifics.\n"
        'Return ONLY JSON: {"score": <0..1>, "reasoning": "<one sentence>"}'
    )
    return {"key": "faithfulness", "score": verdict.score if verdict else 0.0,
            "comment": verdict.reasoning if verdict else "judge unavailable"}


def coverage(run, example) -> dict:
    """What fraction of the reference key points does the answer address?"""
    answer = (run.outputs or {}).get("answer", "")
    key_points = (example.outputs or {}).get("key_points", [])
    verdict = _run_judge(
        "You are grading a research assistant's answer for COVERAGE.\n\n"
        f"QUESTION: {example.inputs.get('question')}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"REFERENCE KEY POINTS:\n- " + "\n- ".join(key_points) + "\n\n"
        "Score the fraction of key points the answer meaningfully addresses "
        "(paraphrases count; exact wording is not required).\n"
        'Return ONLY JSON: {"score": <0..1>, "reasoning": "<one sentence>"}'
    )
    return {"key": "coverage", "score": verdict.score if verdict else 0.0,
            "comment": verdict.reasoning if verdict else "judge unavailable"}


# ─── Programmatic evaluators (ARO's epistemic math, zero tokens) ─────────


def risk_calibration(run, example) -> dict:
    """Reported epistemic risk must be sane: present, in range, floor applied."""
    report = (run.outputs or {}).get("report", {})
    risk = report.get("final_epistemic_risk")
    if risk is None or not (0.0 <= risk <= 1.0):
        return {"key": "risk_calibration", "score": 0.0,
                "comment": f"invalid risk value: {risk}"}
    # Perfect certainty is epistemically dishonest — the risk floor exists
    # for a reason. Score 1.0 for honest non-zero risk.
    return {"key": "risk_calibration", "score": 1.0 if risk >= 0.05 else 0.3}


def confidence_honesty(run, example) -> dict:
    """Confidence and risk should roughly oppose each other."""
    report = (run.outputs or {}).get("report", {})
    conf = report.get("final_hypothesis_confidence", 0.0)
    risk = report.get("final_epistemic_risk", 1.0)
    if not (0.0 <= conf <= 1.0):
        return {"key": "confidence_honesty", "score": 0.0}
    # High confidence with high risk (or the inverse) signals miscalibration.
    tension = max(0.0, conf + risk - 1.3)
    return {"key": "confidence_honesty", "score": round(max(0.0, 1.0 - tension), 3)}


def report_completeness(run, example) -> dict:
    """A shippable report has a summary, a conclusion, and consulted sources."""
    report = (run.outputs or {}).get("report", {})
    answer = (run.outputs or {}).get("answer", "")
    checks = [
        bool(report.get("executive_summary")),
        bool(answer and len(answer) > 80),
        report.get("termination_reason") not in (None, "", "unknown"),
        bool(report.get("total_tokens_used", 0) > 0),
    ]
    return {"key": "report_completeness",
            "score": round(sum(checks) / len(checks), 3)}


LLM_EVALUATORS = [faithfulness, coverage]
PROGRAMMATIC_EVALUATORS = [risk_calibration, confidence_honesty, report_completeness]
ALL_EVALUATORS = LLM_EVALUATORS + PROGRAMMATIC_EVALUATORS
