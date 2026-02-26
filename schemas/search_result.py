"""
Search Result Schema
====================
Typed model for web search results.
Used across all search engines for consistent data handling.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single web search result from any engine."""

    title: str = Field(..., description="Result title")
    url: str = Field(..., description="Result URL")
    snippet: str = Field(default="", description="Result snippet/description")
    source_type: Literal[
        "web", "academic_paper", "preprint", "academic", "encyclopedia"
    ] = Field(default="web", description="Type of source")
    query: str = Field(default="", description="The query that produced this result")
    full_content: Optional[str] = Field(
        None, description="Full page content (populated after extraction)"
    )
