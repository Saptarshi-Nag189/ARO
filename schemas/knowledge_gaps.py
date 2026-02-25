"""
Knowledge Gap Schemas
=====================
Model for tracking unresolved research gaps.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class KnowledgeGap(BaseModel):
    """An identified gap in the current research knowledge."""

    id: Optional[str] = Field(None, description="Unique gap identifier")
    description: str = Field(..., description="Description of the knowledge gap")
    severity: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Severity of the gap (0 = minor, 1 = critical)"
    )
    related_hypothesis_ids: List[str] = Field(
        default_factory=list,
        description="Hypotheses affected by this gap"
    )
    suggested_queries: Optional[List[str]] = Field(
        default_factory=list,
        description="Suggested search queries to resolve this gap"
    )
    resolved: bool = Field(
        default=False,
        description="Whether this gap has been resolved"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(None)


class KnowledgeGapList(BaseModel):
    """A list of knowledge gaps."""
    gaps: List[KnowledgeGap] = Field(default_factory=list)
