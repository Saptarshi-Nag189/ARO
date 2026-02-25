"""
Report Schemas
==============
Final report and innovation proposal data models.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap


class InnovationProposal(BaseModel):
    """A patent-grade innovation proposal."""
    title: str = Field(..., description="Proposal title")
    description: str = Field(..., description="Full description")
    differentiation_summary: str = Field(
        ..., description="How it differs from prior art"
    )
    novelty_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Calculated novelty score"
    )
    novelty_interpretation: str = Field(
        default="derivative",
        description="patent-grade / incremental / derivative"
    )
    prior_art_references: List[str] = Field(default_factory=list)
    addressed_knowledge_gaps: List[str] = Field(default_factory=list)


class IterationMetrics(BaseModel):
    """Metrics for a single research iteration."""
    iteration: int
    hypothesis_confidence: float  # (effective confidence)
    raw_confidence: float = 0.0
    epistemic_risk: float
    risk_floor_applied: bool = False
    novelty_score: float
    new_claims_count: int
    total_claims_count: int
    total_sources_count: int
    unresolved_gaps_count: int
    gap_count_before: int = 0
    gap_count_after: int = 0
    contradiction_cycle_count: int = 0
    token_usage: int = 0
    execution_time_seconds: float = 0.0


class FinalReport(BaseModel):
    """The final structured research report."""

    session_id: str = Field(..., description="Session identifier")
    research_objective: str = Field(
        ..., description="The original research objective"
    )
    executive_summary: str = Field(
        ..., description="Executive summary of findings"
    )
    conclusion: str = Field(
        default="",
        description="Clear, direct conclusion that answers the research objective"
    )
    mode: str = Field(
        ..., description="Operation mode used (interactive/autonomous/innovation)"
    )

    # Core findings
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    key_claims: List[Claim] = Field(default_factory=list)
    knowledge_gaps: List[KnowledgeGap] = Field(default_factory=list)

    # Scores
    final_epistemic_risk: float = Field(default=1.0)
    final_novelty_score: float = Field(default=0.0)
    final_hypothesis_confidence: float = Field(default=0.0)

    # Innovation (only in innovation mode)
    innovation_proposals: Optional[List[InnovationProposal]] = Field(
        default_factory=list
    )

    # Metrics history
    iteration_metrics: List[IterationMetrics] = Field(default_factory=list)

    # Metadata
    total_iterations: int = Field(default=0)
    total_tokens_used: int = Field(default=0)
    total_execution_time_seconds: float = Field(default=0.0)
    termination_reason: str = Field(default="unknown")
    created_at: datetime = Field(default_factory=datetime.utcnow)
