"""
Reflection Agent
================
Meta-analysis of the research state — assesses gaps, trends,
and recommends strategy adjustments.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import ReflectionOutput


class ReflectionAgent(BaseAgent):
    """Provides meta-analysis and strategy recommendations."""

    def __init__(self, gateway):
        super().__init__("reflection", gateway)

    def get_system_prompt(self) -> str:
        base_prompt = (
            "You are a Reflection Agent. Your role is to perform meta-analysis "
            "of the entire research state and recommend strategy adjustments.\n\n"
            "You must:\n"
            "1. Provide a META-ANALYSIS of the current research state\n"
            "2. Describe CONFIDENCE TRENDS — are we converging or diverging?\n"
            "3. Assess remaining KNOWLEDGE GAPS — which are critical?\n"
            "4. Suggest STRATEGY ADJUSTMENTS for the next iteration:\n"
            "   - What area needs more attention?\n"
            "   - What approach should change?\n"
            "   - Why the change is recommended?\n"
            "5. Provide ADVISORY STOP SIGNALS only (advisory_should_stop, "
            "advisory_reason, epistemic_risk).\n\n"
            "IMPORTANT: You do NOT control loop termination. "
            "The orchestrator decides deterministically.\n\n"
            "Consider the iteration metrics: confidence scores, risk levels, "
            "and novelty trends when making your assessment.\n\n"
            "Return strict JSON with these key fields:\n"
            "- epistemic_risk\n"
            "- advisory_should_stop\n"
            "- advisory_reason"
        )

        mode = getattr(self.gateway.config, "mode", "production")
        if mode == "audit":
            base_prompt += (
                "\n\n[AUDIT MODE ACTIVE]\n"
                "You may use any reasoning traces you internally generated to inform your meta-analysis, "
                "but you MUST NOT output the reasoning traces or any raw internal thoughts in the final JSON. "
                "You must strictly output ONLY the requested valid JSON format."
            )

        return base_prompt

    def get_output_schema(self) -> Type[BaseModel]:
        return ReflectionOutput
