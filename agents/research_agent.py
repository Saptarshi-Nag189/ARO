"""
Research Agent
==============
Takes a research plan and produces raw research findings with source metadata.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import ResearchOutput


class ResearchAgent(BaseAgent):
    """Conducts research based on a plan and returns raw findings."""

    def __init__(self, gateway):
        super().__init__("research", gateway)

    def get_system_prompt(self) -> str:
        return (
            "You are a Research Agent. Your role is to analyze and synthesize research "
            "findings from real web search results provided in the prompt.\n\n"
            "CRITICAL RULES:\n"
            "1. You will receive REAL web search results (from DuckDuckGo, Semantic Scholar, "
            "arXiv, OpenAlex, Wikipedia). Use these as your PRIMARY sources.\n"
            "2. For each finding, use the EXACT title and URL from the search results.\n"
            "3. DO NOT invent, fabricate, or hallucinate any sources or URLs.\n"
            "4. If no web results are available, clearly state you are using training knowledge.\n"
            "5. Rate credibility based on source type:\n"
            "   - Peer-reviewed papers: 0.85-0.95\n"
            "   - arXiv preprints: 0.7-0.85\n"
            "   - Wikipedia: 0.6-0.75\n"
            "   - Web articles: 0.5-0.7\n"
            "   - Training knowledge (no source): 0.3-0.5\n\n"
            "For each finding:\n"
            "1. Provide the key content/information discovered\n"
            "2. Cite the EXACT source title and URL from the search results\n"
            "3. Estimate the source's credibility using the scale above\n"
            "4. Rate the finding's relevance to the research objective (0-1)\n\n"
            "Report the search queries used and how many sources you consulted."
        )

    def get_output_schema(self) -> Type[BaseModel]:
        return ResearchOutput
