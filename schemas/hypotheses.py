"""
Hypothesis Schemas
==================
Hypothesis data model with claim linkage.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class HypothesisStatus(str, Enum):
    """Current status of a hypothesis."""
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    REFUTED = "refuted"
    MERGED = "merged"


class Hypothesis(BaseModel):
    """A research hypothesis linked to supporting/opposing claims."""

    id: Optional[str] = Field(None, description="Unique hypothesis identifier")
    statement: str = Field(..., description="The hypothesis statement")
    supporting_claim_ids: List[str] = Field(
        default_factory=list,
        description="IDs of claims that support this hypothesis"
    )
    opposing_claim_ids: List[str] = Field(
        default_factory=list,
        description="IDs of claims that oppose this hypothesis"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Calculated confidence score"
    )
    status: HypothesisStatus = Field(
        default=HypothesisStatus.PROPOSED,
        description="Current status of the hypothesis"
    )
    related_hypothesis_ids: List[str] = Field(
        default_factory=list,
        description="IDs of related hypotheses (for graph edges)"
    )
    knowledge_gap_ids: List[str] = Field(
        default_factory=list,
        description="IDs of knowledge gaps related to this hypothesis"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HypothesisList(BaseModel):
    """A list of hypotheses."""
    hypotheses: List[Hypothesis] = Field(default_factory=list)
