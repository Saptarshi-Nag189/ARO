"""
Claim Schemas
=============
Atomic claim data model with deduplication support.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """An atomic, source-backed knowledge claim."""

    id: Optional[str] = Field(None, description="Unique claim identifier")
    subject: str = Field(..., description="The entity or concept the claim is about")
    relation: str = Field(..., description="The relationship or predicate")
    object: str = Field(..., description="The target entity or value")
    qualifiers: Optional[List[str]] = Field(
        default_factory=list,
        description="Contextual qualifiers (e.g., 'as of 2024', 'in mammals')"
    )
    source_id: str = Field(..., description="Reference to the source this claim was extracted from")
    confidence_estimate: float = Field(
        ..., ge=0.0, le=1.0,
        description="Model-estimated confidence in the claim's accuracy"
    )
    credibility_weight: float = Field(
        ..., ge=0.0, le=1.0,
        description="Weight derived from source credibility"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the claim was created or last updated"
    )
    merged_from: Optional[List[str]] = Field(
        default_factory=list,
        description="IDs of claims this was merged from (deduplication)"
    )
    evidence_count: int = Field(
        default=1,
        description="Number of independent evidence sources supporting this claim"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "subject": "Transformer architecture",
                "relation": "was_introduced_by",
                "object": "Vaswani et al. 2017",
                "qualifiers": ["in the paper 'Attention Is All You Need'"],
                "source_id": "src_001",
                "confidence_estimate": 0.95,
                "credibility_weight": 0.9,
            }
        }


class ClaimList(BaseModel):
    """A list of claims, typically returned by claim extraction."""
    claims: List[Claim] = Field(default_factory=list)
