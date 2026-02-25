"""
Source Schemas
==============
Source registry data model.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A research source with credibility scoring."""

    id: Optional[str] = Field(None, description="Unique source identifier")
    url: Optional[str] = Field(None, description="URL of the source")
    title: str = Field(..., description="Title or name of the source")
    authors: Optional[List[str]] = Field(
        default_factory=list,
        description="Authors of the source"
    )
    publication_date: Optional[str] = Field(
        None, description="Publication date if known"
    )
    source_type: str = Field(
        default="web",
        description="Type of source (web, paper, book, expert, etc.)"
    )
    credibility_score: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Assessed credibility of this source"
    )
    content_summary: Optional[str] = Field(
        None, description="Brief summary of the source content"
    )
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this source was retrieved"
    )


class SourceList(BaseModel):
    """A list of sources."""
    sources: List[Source] = Field(default_factory=list)
