"""
Innovation Agent
================
Generates patent-grade innovation proposals based on hypotheses,
knowledge gaps, and prior-art analysis.
GUARDRAIL: No innovation without prior-art scan.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import InnovationOutput


class InnovationAgent(BaseAgent):
    """Generates innovation proposals with novelty assessment."""

    def __init__(self, gateway):
        super().__init__("innovation", gateway)

    def get_system_prompt(self) -> str:
        return (
            "You are an Innovation Agent. Your role is to generate novel "
            "innovation proposals based on the research findings, hypotheses, "
            "and identified knowledge gaps.\n\n"
            "You must:\n"
            "1. Analyze the provided PRIOR ART SUMMARY\n"
            "2. Generate INNOVATION PROPOSALS that:\n"
            "   - Have a clear title and detailed description\n"
            "   - Clearly differentiate from prior art\n"
            "   - Reference specific prior art pieces\n"
            "   - Address identified knowledge gaps\n"
            "   - Include a self-estimated novelty score (0-1)\n"
            "3. Provide an OVERALL NOVELTY ASSESSMENT\n\n"
            "Novelty scoring guide:\n"
            "  > 0.75 = potentially patent-grade innovation\n"
            "  0.6-0.75 = incremental improvement\n"
            "  < 0.6 = derivative work\n\n"
            "Be ambitious but honest. Clearly state what is truly novel vs. "
            "what is a recombination of existing ideas."
        )

    def get_output_schema(self) -> Type[BaseModel]:
        return InnovationOutput
