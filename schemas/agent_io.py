"""
Agent I/O Contract Schemas
==========================
Strict input/output contracts for each agent.
All agents must return structured JSON matching these schemas.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap
from schemas.sources import Source


# ─── Planner Agent ────────────────────────────────────────────────────────────

class ResearchSubQuestion(BaseModel):
    """A decomposed sub-question from the research plan."""
    question: str = Field(..., description="The sub-question to investigate")
    priority: int = Field(default=1, ge=1, le=5, description="Priority 1 (highest) to 5 (lowest)")
    search_strategy: str = Field(
        default="general",
        description="Suggested search approach (general, academic, patent, expert)"
    )


class PlannerOutput(BaseModel):
    """Output from the Planner Agent."""
    research_objective_summary: str = Field(
        ..., description="Restated research objective"
    )
    sub_questions: List[ResearchSubQuestion] = Field(
        ..., description="Decomposed sub-questions"
    )
    iteration_targets: List[str] = Field(
        default_factory=list,
        description="Specific targets for this iteration"
    )
    recommended_sources: Optional[List[str]] = Field(
        default_factory=list,
        description="Suggested sources or search terms"
    )


# ─── Research Agent ───────────────────────────────────────────────────────────

class ResearchFinding(BaseModel):
    """A raw research finding with its source."""
    content: str = Field(..., description="The raw finding text")
    source_title: str = Field(..., description="Title of the source")
    source_url: Optional[str] = Field(None, description="URL if available")
    credibility_estimate: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Estimated credibility of this source"
    )
    relevance: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Relevance to the research objective"
    )


class ResearchOutput(BaseModel):
    """Output from the Research Agent."""
    findings: List[ResearchFinding] = Field(
        ..., description="Raw research findings"
    )
    sources_consulted: int = Field(
        default=0, description="Number of sources consulted"
    )
    search_queries_used: List[str] = Field(
        default_factory=list,
        description="Search queries that were used"
    )


# ─── Claim Extraction Agent ──────────────────────────────────────────────────

class ClaimExtractionOutput(BaseModel):
    """Output from the Claim Extraction Agent."""
    claims: List[Claim] = Field(
        ..., description="Extracted atomic claims"
    )
    extraction_notes: Optional[str] = Field(
        None, description="Notes about ambiguous or uncertain extractions"
    )


# ─── Skeptic Agent ────────────────────────────────────────────────────────────

class Contradiction(BaseModel):
    """An identified contradiction between claims or hypotheses."""
    claim_id_a: str = Field(..., description="First conflicting claim ID")
    claim_id_b: str = Field(..., description="Second conflicting claim ID")
    description: str = Field(..., description="Nature of the contradiction")
    severity: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="How severe the contradiction is"
    )


class CredibilityChallenge(BaseModel):
    """A challenge to the credibility of a claim or source."""
    target_id: str = Field(..., description="Claim or source ID being challenged")
    reason: str = Field(..., description="Reason for the challenge")
    suggested_adjustment: float = Field(
        default=0.0, ge=-1.0, le=0.0,
        description="Suggested adjustment to credibility (-1 to 0)"
    )


class SkepticOutput(BaseModel):
    """Output from the Skeptic Agent."""
    contradictions: List[Contradiction] = Field(
        default_factory=list,
        description="Identified contradictions"
    )
    credibility_challenges: List[CredibilityChallenge] = Field(
        default_factory=list,
        description="Credibility challenges raised"
    )
    knowledge_gaps: List[KnowledgeGap] = Field(
        default_factory=list,
        description="New knowledge gaps identified"
    )
    overall_assessment: str = Field(
        ..., description="Overall skeptical assessment of current knowledge state"
    )


# ─── Synthesis Agent ─────────────────────────────────────────────────────────

class HypothesisRelationship(BaseModel):
    """A typed relationship between two hypotheses."""
    source_hypothesis_id: str = Field(
        ..., description="Source hypothesis ID"
    )
    target_hypothesis_id: str = Field(
        ..., description="Target hypothesis ID"
    )
    relationship_type: str = Field(
        ..., description="Type of relationship (e.g., supports/refines/conflicts_with)"
    )


class SynthesisOutput(BaseModel):
    """Output from the Synthesis Agent."""
    hypotheses: List[Hypothesis] = Field(
        ...,
        max_length=8,
        description="Synthesized hypotheses (max 8)"
    )
    merged_claims: Optional[List[str]] = Field(
        default_factory=list,
        max_length=100,
        description="Claim IDs that were merged during synthesis (max 100)"
    )
    narrative_summary: str = Field(
        ...,
        max_length=1500,
        description="Narrative summary of synthesized findings"
    )
    relationships: Optional[List[HypothesisRelationship]] = Field(
        default_factory=list,
        max_length=12,
        description="Discovered relationships between hypotheses (max 12)"
    )


# ─── Innovation Agent ────────────────────────────────────────────────────────

class InnovationProposalIO(BaseModel):
    """An innovation proposal from the Innovation Agent."""
    title: str = Field(..., description="Title of the innovation proposal")
    description: str = Field(..., description="Detailed description")
    differentiation: str = Field(
        ..., description="How this differs from prior art"
    )
    prior_art_references: List[str] = Field(
        default_factory=list,
        description="References to relevant prior art"
    )
    estimated_novelty: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Self-estimated novelty score"
    )
    addressed_gaps: List[str] = Field(
        default_factory=list,
        description="Knowledge gap IDs this proposal addresses"
    )


class InnovationOutput(BaseModel):
    """Output from the Innovation Agent."""
    proposals: List[InnovationProposalIO] = Field(
        ..., description="Innovation proposals"
    )
    prior_art_summary: str = Field(
        ..., description="Summary of prior art scan"
    )
    overall_novelty_assessment: str = Field(
        ..., description="Assessment of novelty landscape"
    )


# ─── Reflection Agent ────────────────────────────────────────────────────────

class StrategyAdjustment(BaseModel):
    """A suggested adjustment to the research strategy."""
    area: str = Field(..., description="Area needing adjustment")
    current_approach: str = Field(..., description="What we're currently doing")
    suggested_change: str = Field(..., description="What we should do instead")
    rationale: str = Field(..., description="Why this change is recommended")


class ReflectionOutput(BaseModel):
    """Output from the Reflection Agent."""
    meta_analysis: str = Field(
        ..., description="Meta-analysis of the current research state"
    )
    confidence_trend: str = Field(
        ..., description="Description of confidence trends"
    )
    gap_assessment: str = Field(
        ..., description="Assessment of remaining knowledge gaps"
    )
    strategy_adjustments: List[StrategyAdjustment] = Field(
        default_factory=list,
        description="Suggested strategy adjustments"
    )
    epistemic_risk: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Reflection-estimated epistemic risk (advisory only)"
    )
    advisory_should_stop: bool = Field(
        default=False,
        description="Advisory opinion on whether to stop (advisory only)"
    )
    advisory_reason: str = Field(
        ..., description="Rationale for stop/continue advisory"
    )
