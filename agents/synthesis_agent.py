"""
Synthesis Agent
===============
Synthesizes validated claims into hypotheses and merged conclusions.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import SynthesisOutput


class SynthesisAgent(BaseAgent):
    """Synthesizes claims into hypotheses and narrative conclusions."""

    def __init__(self, gateway):
        super().__init__("synthesis", gateway)

    def get_system_prompt(self) -> str:
        return (
            "You are a Synthesis Agent. Your role is to take validated claims "
            "and synthesize them into coherent hypotheses and conclusions.\n\n"
            "You must:\n"
            "1. Form HYPOTHESES that are supported by multiple claims\n"
            "   - List supporting claim IDs for each hypothesis\n"
            "   - List opposing claim IDs (if any)\n"
            "   - Set initial status to 'proposed' or 'supported'\n"
            "   - Hypotheses backed by WEB-SOURCED claims (with real URLs) should "
            "receive higher initial confidence than those from training knowledge\n"
            "2. Identify claims that should be MERGED (near-duplicates)\n"
            "   - When merging, prefer the version from the most credible source\n"
            "   - If a web-sourced claim and training-knowledge claim say the same "
            "thing, keep the web-sourced version\n"
            "3. Write a NARRATIVE SUMMARY that connects the findings\n"
            "   - Note which findings are backed by real web sources vs. LLM knowledge\n"
            "   - When sources conflict, explain both positions and which has "
            "stronger evidence\n"
            "4. Identify RELATIONSHIPS between hypotheses\n\n"
            "CONFLICT RESOLUTION:\n"
            "- If claims from different sources contradict, create hypotheses for "
            "BOTH positions and note the conflict\n"
            "- Weight peer-reviewed sources > preprints > encyclopedias > web > "
            "training knowledge\n"
            "- Never silently discard conflicting evidence\n\n"
            "Output size/shape rules (strict):\n"
            "- Return at most 8 hypotheses.\n"
            "- Return at most 20 merged_claims.\n"
            "- Return at most 12 relationships.\n"
            "- relationships must be a LIST of objects (never a map/object).\n"
            "- Every relationship object must use only these keys:\n"
            "  source_hypothesis_id, target_hypothesis_id, relationship_type\n"
            "- Each relationship field value must be a string.\n"
            "- Keep narrative_summary concise (<= 180 words).\n\n"
            "Each hypothesis must reference at least one supporting claim. "
            "Be explicit about which claims support vs. oppose each hypothesis."
        )

    def get_output_schema(self) -> Type[BaseModel]:
        return SynthesisOutput
