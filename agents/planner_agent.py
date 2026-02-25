"""
Planner Agent
=============
Takes a research objective and decomposes it into sub-questions,
search strategies, and iteration targets.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import PlannerOutput


class PlannerAgent(BaseAgent):
    """Decomposes a research objective into an actionable research plan."""

    def __init__(self, gateway):
        super().__init__("planner", gateway)

    def get_system_prompt(self) -> str:
        return (
            "You are a Research Planner Agent. Your role is to analyze a research "
            "objective and decompose it into specific, answerable sub-questions.\n\n"
            "For each sub-question, assign a priority (1=highest, 5=lowest) and "
            "suggest a search strategy (general, academic, patent, expert).\n\n"
            "Also identify specific targets for the current iteration and recommend "
            "useful sources or search terms.\n\n"
            "Be thorough but focused. Prioritize questions that will yield the "
            "highest-impact findings first."
        )

    def get_output_schema(self) -> Type[BaseModel]:
        return PlannerOutput
