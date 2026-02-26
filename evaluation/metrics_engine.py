"""
Metrics Engine
==============
Calculates and tracks iteration-level metrics (confidence, risk, novelty).
Extracted from the Orchestrator to simplify the main pipeline loop.

Aligned with: evaluation/confidence.py, evaluation/risk.py, evaluation/novelty.py,
              schemas/reports.py (IterationMetrics)
"""

from typing import List, Any, Optional
from evaluation.confidence import (
    compute_hypothesis_confidence,
    compute_effective_confidence,
)
from evaluation.risk import compute_epistemic_risk, compute_average_uncertainty
from evaluation.novelty import (
    compute_novelty_score,
    compute_contradiction_resolution_score,
    compute_knowledge_gap_coverage,
)
from schemas.reports import IterationMetrics
import logging

logger = logging.getLogger("aro.metrics_engine")


class MetricsEngine:
    """Computes and tracks metrics across research iterations."""

    def __init__(self, config, memory_service):
        self.config = config
        self.memory = memory_service
        self.iteration_metrics: List[IterationMetrics] = []
        self.total_contradictions = 0
        self.resolved_contradictions = 0
        self.contradiction_cycle_count = 0
        self.skeptic_detected_gap_count = 0

    def record_contradictions(self, contradiction_count: int) -> None:
        """Record newly found contradictions."""
        self.total_contradictions += contradiction_count
        if contradiction_count > 0:
            self.contradiction_cycle_count += 1

    def record_skeptic_gaps(self, gap_count: int) -> None:
        """Track total gap detections for the integrity guardrail."""
        self.skeptic_detected_gap_count += gap_count

    def compute_iteration_metrics(
        self,
        iteration: int,
        prior_art_similarity: float = 0.5,
        gap_count_before: int = 0,
        gap_count_after: int = 0,
        tokens_this_iter: int = 0,
        has_innovations: bool = False,
        new_claims_count: int = 0,
    ) -> IterationMetrics:
        """
        Compute all metrics for an iteration.
        
        Mirrors the logic from Orchestrator._compute_iteration_metrics() exactly.
        """
        all_claims = self.memory.get_all_claims()
        all_hypotheses = self.memory.get_all_hypotheses()
        unresolved_gaps = self.memory.get_unresolved_gaps()

        # 1. Epistemic risk (computed first for effective confidence)
        avg_uncertainty = compute_average_uncertainty(all_claims)
        normalized_gap_severity = self.memory.get_normalized_gap_severity()
        source_cred_variance = self.memory.get_source_credibility_variance()

        epistemic_risk = compute_epistemic_risk(
            average_uncertainty=avg_uncertainty,
            unresolved_contradictions=max(
                0, self.total_contradictions - self.resolved_contradictions
            ),
            total_claims=len(all_claims) if all_claims else 1,
            normalized_gap_severity=normalized_gap_severity,
            source_credibility_variance=source_cred_variance,
            risk_floor=self.config.risk_floor,
        )
        risk_floor_applied = epistemic_risk == self.config.risk_floor

        # 2. Hypothesis confidence & Effective confidence
        avg_raw_confidence = 0.0
        avg_effective_confidence = 0.0
        if all_hypotheses:
            raw_confidences = []
            effective_confidences = []
            for hyp in all_hypotheses:
                supporting = [
                    c for c in all_claims if c.id in hyp.supporting_claim_ids
                ]
                opposing = [
                    c for c in all_claims if c.id in hyp.opposing_claim_ids
                ]

                raw_conf = compute_hypothesis_confidence(
                    supporting, opposing, self.config.epsilon
                )
                eff_conf = compute_effective_confidence(
                    raw_confidence=raw_conf,
                    epistemic_risk=epistemic_risk,
                    supporting_claim_count=len(supporting),
                    opposing_claim_count=len(opposing),
                    contradiction_cycle_count=self.contradiction_cycle_count,
                )

                # Single-source guardrail
                unique_support_sources = {
                    claim.source_id for claim in supporting
                }
                if len(unique_support_sources) < 2:
                    eff_conf = min(eff_conf, 0.85)

                # Update hypothesis confidence in memory
                hyp.confidence = eff_conf
                try:
                    self.memory.update_hypothesis(hyp)
                except Exception:
                    pass

                raw_confidences.append(raw_conf)
                effective_confidences.append(eff_conf)

            avg_raw_confidence = sum(raw_confidences) / len(raw_confidences)
            avg_effective_confidence = sum(effective_confidences) / len(effective_confidences)

        # 3. Novelty score
        graph_bridge = self.memory.get_graph_bridge_score()
        contradiction_resolution = compute_contradiction_resolution_score(
            self.total_contradictions, self.resolved_contradictions
        )
        all_gaps = self.memory.get_all_knowledge_gaps()
        total_gaps = len(all_gaps)
        addressed_gaps = sum(1 for g in all_gaps if g.resolved)
        gap_coverage = compute_knowledge_gap_coverage(total_gaps, addressed_gaps)

        novelty = compute_novelty_score(
            graph_bridge_score=graph_bridge,
            contradiction_resolution_score=contradiction_resolution,
            prior_art_similarity=prior_art_similarity,
            knowledge_gap_coverage=gap_coverage,
        )

        if not has_innovations:
            novelty = min(novelty, 0.5)

        return IterationMetrics(
            iteration=iteration,
            hypothesis_confidence=round(avg_effective_confidence, 6),
            raw_confidence=round(avg_raw_confidence, 6),
            epistemic_risk=epistemic_risk,
            risk_floor_applied=risk_floor_applied,
            novelty_score=novelty,
            new_claims_count=new_claims_count,
            total_claims_count=len(all_claims),
            total_sources_count=self.memory.source_registry.count_sources(),
            unresolved_gaps_count=len(unresolved_gaps),
            gap_count_before=gap_count_before,
            gap_count_after=gap_count_after,
            contradiction_cycle_count=self.contradiction_cycle_count,
            token_usage=tokens_this_iter,
        )

    # ─── Guardrails ───────────────────────────────────────────────────────

    def assert_no_reasoning_artifacts(
        self, payload: Any, context: str
    ) -> None:
        """Reject any reasoning_details fields in structured memory/report payloads."""
        def _walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    next_path = f"{path}.{key}" if path else key
                    if key == "reasoning_details":
                        raise RuntimeError(
                            f"HARD GUARD VIOLATION: reasoning_details found in {context} at {next_path}"
                        )
                    _walk(value, next_path)
                return
            if isinstance(node, list):
                for idx, item in enumerate(node):
                    _walk(item, f"{path}[{idx}]")
                return
            if hasattr(node, "model_dump"):
                _walk(node.model_dump(), path)

        _walk(payload, "")

    def assert_token_accounting(self, total_tokens_used: int) -> None:
        """Ensure iteration token deltas reconcile exactly with session total."""
        iteration_token_sum = sum(m.token_usage for m in self.iteration_metrics)
        if iteration_token_sum != total_tokens_used:
            raise RuntimeError(
                "CRITICAL: Token accounting mismatch. "
                f"sum(iteration token_usage)={iteration_token_sum} "
                f"!= total_tokens_used={total_tokens_used}"
            )

    def assert_gap_integrity(self) -> None:
        """Ensure skeptic-detected gaps were persisted."""
        if self.skeptic_detected_gap_count > 0 and not self.memory.get_all_knowledge_gaps():
            raise RuntimeError(
                "CRITICAL: Skeptic detected one or more knowledge gaps but none persisted."
            )
