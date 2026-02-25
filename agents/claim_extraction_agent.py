"""
Claim Extraction Agent
======================
Takes raw research text and extracts structured atomic claims.
"""

from typing import Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from schemas.agent_io import ClaimExtractionOutput


class ClaimExtractionAgent(BaseAgent):
    """Extracts atomic claims from raw research findings."""

    def __init__(self, gateway):
        super().__init__("claim_extraction", gateway)

    def get_system_prompt(self) -> str:
        return (
            "You are a Claim Extraction Agent. Your role is to parse raw research "
            "findings and extract atomic, verifiable claims.\n\n"
            "Each claim must have:\n"
            "- subject: The entity or concept the claim is about\n"
            "- relation: The relationship or predicate (e.g. 'increases', "
            "'was_invented_by', 'contains', 'outperforms')\n"
            "- object: The target entity or value\n"
            "- qualifiers: Context (e.g. 'in mammals', 'as of 2024'). "
            "Include source provenance: 'web-sourced' for claims from real URLs, "
            "'training-knowledge' for claims without verifiable sources.\n"
            "- source_id: Reference to the source (use the source_id provided)\n"
            "- confidence_estimate: Your confidence in the claim (0-1)\n"
            "- credibility_weight: Weight from source credibility (0-1)\n\n"
            "Rules:\n"
            "1. Each claim must be ATOMIC — one fact per claim\n"
            "2. Claims must be VERIFIABLE — no opinions or vague statements\n"
            "3. Always include source attribution\n"
            "4. Claims from REAL web sources (with URLs) should receive higher "
            "credibility_weight (0.7-0.95) than training-knowledge claims (0.3-0.5)\n"
            "5. When multiple sources say different things about the same topic, "
            "extract BOTH claims — do NOT merge conflicting information\n"
            "6. Add source type in qualifiers (e.g. 'peer-reviewed paper', "
            "'arXiv preprint', 'web article', 'Wikipedia')\n"
            "7. Add any extraction notes for ambiguous cases"
        )

    def get_output_schema(self) -> Type[BaseModel]:
        return ClaimExtractionOutput
