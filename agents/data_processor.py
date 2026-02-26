"""
Data Processor
==============
Handles data parsing, deduplication, and memory persistence logic for the Orchestrator.
Operates on the MemoryService facade — never touches DB directly.

Aligned with: memory_service.py, schemas/claims.py, schemas/sources.py
"""

from typing import List, Dict, Tuple
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.sources import Source
import logging

logger = logging.getLogger("aro.data_processor")


class DataProcessor:
    """Orchestrates complex data transformations and persistence."""

    def __init__(self, memory_service):
        """
        Args:
            memory_service: MemoryService instance (the unified facade).
        """
        self.memory = memory_service

    # ─── Source Registration ──────────────────────────────────────────────

    def register_sources(self, research_output) -> List[Source]:
        """
        Register all sources from research findings via MemoryService.add_source().
        Returns list of persisted Source objects.
        """
        sources = []
        for finding in research_output.findings:
            source = self.memory.add_source(Source(
                title=finding.source_title,
                url=finding.source_url,
                credibility_score=finding.credibility_estimate,
                content_summary=finding.content[:200],
            ))
            sources.append(source)
        return sources

    # ─── Claim Persistence ────────────────────────────────────────────────

    def persist_claims(self, claims_output, sources: List[Source]) -> List[Claim]:
        """
        Persist extracted claims through memory service.
        Maps claim.source_id to actual registered source IDs.

        Returns list of successfully persisted claims.
        """
        persisted = []
        source_ids = [s.id for s in sources]

        for claim in claims_output.claims:
            # Map source_id to an actual registered source
            if claim.source_id not in source_ids:
                # Use the first available source as fallback
                if source_ids:
                    claim.source_id = source_ids[0]
                else:
                    logger.warning(
                        "Skipping claim without valid source: %s", claim.subject
                    )
                    continue
            try:
                persisted_claim = self.memory.add_claim(claim)
                persisted.append(persisted_claim)
            except ValueError as e:
                logger.warning("Guardrail blocked claim: %s", e)

        return persisted

    # ─── Hypothesis Persistence ───────────────────────────────────────────

    def persist_hypotheses(self, synthesis_output, all_claims: List[Claim]) -> None:
        """Persist hypotheses from synthesis output, filtering to valid claim IDs."""
        claim_ids = {c.id for c in all_claims}

        for hyp in synthesis_output.hypotheses:
            # Filter to only existing claim IDs
            valid_supporting = [
                cid for cid in hyp.supporting_claim_ids if cid in claim_ids
            ]
            valid_opposing = [
                cid for cid in hyp.opposing_claim_ids if cid in claim_ids
            ]

            if not valid_supporting:
                if all_claims:
                    valid_supporting = [all_claims[0].id]
                else:
                    logger.warning(
                        "Skipping hypothesis without supporting claims: %s",
                        hyp.statement[:80],
                    )
                    continue

            hyp.supporting_claim_ids = valid_supporting
            hyp.opposing_claim_ids = valid_opposing

            try:
                existing = self.memory.get_hypothesis(hyp.id) if hyp.id else None
                if existing:
                    self.memory.update_hypothesis(hyp)
                else:
                    self.memory.add_hypothesis(hyp)
            except ValueError as e:
                logger.warning("Guardrail blocked hypothesis: %s", e)

    # ─── Skeptic Output Processing ────────────────────────────────────────

    def process_skeptic_output(self, skeptic_output) -> List[tuple]:
        """
        Process skeptic findings — update credibility and persist gaps.

        Returns:
            List of contradiction tuples (claim_id_a, claim_id_b) where severity > 0.
        """
        positive_contradictions = [
            (c.claim_id_a, c.claim_id_b)
            for c in skeptic_output.contradictions
            if c.severity > 0
        ]

        # Apply credibility challenges
        for challenge in skeptic_output.credibility_challenges:
            try:
                current_source = self.memory.get_source(challenge.target_id)
                if current_source:
                    new_score = max(
                        0.0,
                        current_source.credibility_score + challenge.suggested_adjustment,
                    )
                    self.memory.update_source_credibility(
                        challenge.target_id, new_score
                    )
            except Exception as e:
                logger.debug("Could not apply credibility challenge: %s", e)

        # Add new knowledge gaps
        for gap in skeptic_output.knowledge_gaps:
            try:
                self.memory.add_knowledge_gap(gap)
            except Exception:
                logger.critical(
                    "CRITICAL: Failed to persist skeptic knowledge gap. "
                    "Aborting run for data integrity."
                )
                raise

        return positive_contradictions

    # ─── Contradiction Influence ──────────────────────────────────────────

    def apply_contradiction_influence(
        self, contradiction_pairs: List[tuple]
    ) -> None:
        """
        Map contradiction pairs into opposing evidence on supported hypotheses.
        """
        if not contradiction_pairs:
            return

        hypotheses = self.memory.get_all_hypotheses()
        for hyp in hypotheses:
            supporting_ids = set(hyp.supporting_claim_ids)
            opposing_ids = set(hyp.opposing_claim_ids)
            changed = False

            for claim_a, claim_b in contradiction_pairs:
                if claim_a in supporting_ids and claim_b not in opposing_ids:
                    opposing_ids.add(claim_b)
                    changed = True
                if claim_b in supporting_ids and claim_a not in opposing_ids:
                    opposing_ids.add(claim_a)
                    changed = True

            if changed:
                hyp.opposing_claim_ids = sorted(opposing_ids)
                self.memory.update_hypothesis(hyp)
