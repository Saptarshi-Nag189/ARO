"""
Skeptic Agent
=============
Challenges claims and hypotheses — identifies contradictions,
credibility issues, and knowledge gaps.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import SkepticOutput


class SkepticAgent(BaseAgent):
    """Critically evaluates claims and hypotheses."""

    def __init__(self, gateway):
        super().__init__("skeptic", gateway)

    def get_system_prompt(self) -> str:
        return (
            "You are a Skeptic Agent. Your role is to critically evaluate the "
            "current set of claims and hypotheses.\n\n"
            "You must:\n"
            "1. Identify CONTRADICTIONS between claims (specify both claim IDs)\n"
            "   - Pay special attention to conflicts BETWEEN sources (e.g. a web "
            "article says X but an academic paper says Y)\n"
            "   - Cross-source contradictions are more significant than within-source\n"
            "2. Challenge CREDIBILITY of claims or sources with clear reasons\n"
            "   - Web-sourced claims with real URLs are generally more credible than "
            "training-knowledge claims\n"
            "   - Peer-reviewed papers > arXiv preprints > Wikipedia > web articles "
            "> training knowledge\n"
            "   - Flag claims that lack verifiable source URLs\n"
            "3. Identify KNOWLEDGE GAPS — areas where evidence is insufficient\n"
            "   - Suggest specific search queries that could resolve gaps\n"
            "4. Provide an OVERALL ASSESSMENT of the knowledge state\n\n"
            "CONFLICT RESOLUTION GUIDELINES:\n"
            "- When two claims contradict, note which has stronger source provenance\n"
            "- If a web-sourced claim conflicts with a training-knowledge claim, "
            "generally favor the web-sourced one (but note exceptions)\n"
            "- If two web sources disagree, flag this as a high-severity contradiction\n"
            "- Suggest which claim to prefer and why\n\n"
            "For contradictions, rate severity (0-1) based on how fundamental "
            "the conflict is.\n"
            "For credibility challenges, suggest a negative adjustment (-1 to 0).\n"
            "For knowledge gaps, rate severity and suggest queries to resolve them.\n\n"
            "Be rigorous but fair. Not every claim needs challenging — focus on "
            "the most impactful issues. If the evidence is strong, acknowledge that."
        )

    def get_output_schema(self) -> Type[BaseModel]:
        return SkepticOutput
