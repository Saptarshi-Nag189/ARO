"""
Research State
==============
The typed LangGraph state shared by every node in the research graph.

Everything in here must be checkpoint-serializable (LangGraph's
JsonPlusSerializer handles Pydantic models natively), so runs can be
suspended, resumed after a crash, and time-travelled. Live services
(MemoryService, chat models, event emitters) deliberately live OUTSIDE
the state — they are closed over by the nodes via GraphServices.
"""

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict

from schemas.agent_io import (
    InnovationOutput,
    PlannerOutput,
    ReflectionOutput,
    ResearchOutput,
    SkepticOutput,
    SynthesisOutput,
)
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap
from schemas.reports import FastReport, FinalReport, IterationMetrics


def accumulate_or_reset(existing: Optional[list], new: Any) -> list:
    """Reducer: append entries from parallel nodes, reset with the sentinel.

    The `record` node returns "__reset__" after flushing the accumulated
    agent-call log entries into the iteration log, so each iteration
    starts with a clean list.
    """
    existing = existing or []
    if new == "__reset__":
        return []
    if isinstance(new, list):
        return existing + new
    return existing + [new]


class ResearchState(TypedDict, total=False):
    # ── Run inputs (set once at START) ───────────────────────────────
    objective: str
    mode: str            # autonomous | interactive | innovation
    hitl: bool           # True -> interrupt() after each iteration (CLI interactive)

    # ── Loop position ────────────────────────────────────────────────
    iteration: int

    # ── Per-iteration working outputs ────────────────────────────────
    plan: Optional[PlannerOutput]
    web_context: str
    research_output: Optional[ResearchOutput]
    source_ids: List[str]
    new_claim_ids: List[str]
    new_high_confidence_claims: int
    gap_count_before: int
    gap_count_after: int
    # Snapshots taken by single-writer nodes so the parallel fan-out
    # branches (skeptic ‖ synthesis, innovation ‖ reflection) are pure
    # LLM calls that never touch the database concurrently.
    claims_snapshot: List[Claim]
    hypotheses_snapshot: List[Hypothesis]
    gaps_snapshot: List[KnowledgeGap]
    skeptic_output: Optional[SkepticOutput]
    synthesis_output: Optional[SynthesisOutput]
    innovation_output: Optional[InnovationOutput]
    reflection_output: Optional[ReflectionOutput]
    prior_art: Dict[str, Any]
    prior_art_similarity: float
    current_metrics: Optional[IterationMetrics]

    # ── Accumulators ─────────────────────────────────────────────────
    # tokens_used has an additive reducer because parallel branches
    # each report their own usage in the same superstep.
    tokens_used: Annotated[int, operator.add]
    agent_calls: Annotated[list, accumulate_or_reset]
    iteration_metrics: List[IterationMetrics]
    risk_history: List[float]
    novelty_history: List[float]
    new_claims_history: List[int]
    total_contradictions: int
    resolved_contradictions: int
    contradiction_cycle_count: int
    skeptic_detected_gap_count: int
    last_token_snapshot: int
    iteration_started_at: float

    # ── Control flow ─────────────────────────────────────────────────
    need_replan: bool
    human_directive: Optional[str]
    should_stop: bool
    termination_reason: str

    # ── Output ───────────────────────────────────────────────────────
    final_report: Optional[FinalReport]


class FastState(TypedDict, total=False):
    """State for the single-pass fast graph."""

    objective: str
    seed_results: List[dict]
    plan_dict: Dict[str, Any]
    search_results: List[dict]
    tokens_used: Annotated[int, operator.add]
    fast_report: Optional[FastReport]
    final_report: Optional[FinalReport]
    started_at: float
