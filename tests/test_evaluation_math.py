"""Unit tests for the mathematical scoring layer (used as CI-time and
LangSmith evaluators, so their correctness gates everything else)."""

from evaluation.confidence import (
    compute_effective_confidence,
    compute_hypothesis_confidence,
    compute_opposition_score,
    compute_support_score,
)
from evaluation.novelty import (
    compute_contradiction_resolution_score,
    compute_knowledge_gap_coverage,
    compute_novelty_score,
    interpret_novelty,
)
from evaluation.risk import compute_epistemic_risk
from evaluation.termination import TerminationChecker
from schemas.claims import Claim


def _claim(conf: float, cred: float, source="src_1") -> Claim:
    return Claim(
        subject="s", relation="r", object="o",
        source_id=source, confidence_estimate=conf, credibility_weight=cred,
    )


class TestConfidence:
    def test_support_score_is_confidence_times_credibility(self):
        claims = [_claim(0.8, 0.5), _claim(0.5, 0.4)]
        assert abs(compute_support_score(claims) - (0.4 + 0.2)) < 1e-9

    def test_unopposed_hypothesis_approaches_one(self):
        conf = compute_hypothesis_confidence([_claim(0.9, 0.9)], [])
        assert conf > 0.99

    def test_equal_opposition_halves_confidence(self):
        sup = [_claim(0.8, 0.8)]
        opp = [_claim(0.8, 0.8)]
        conf = compute_hypothesis_confidence(sup, opp)
        assert abs(conf - 0.5) < 1e-3

    def test_no_evidence_is_zero(self):
        assert compute_hypothesis_confidence([], []) == 0.0

    def test_effective_confidence_never_exceeds_raw(self):
        raw = 0.9
        eff = compute_effective_confidence(
            raw_confidence=raw,
            epistemic_risk=0.5,
            supporting_claim_count=2,
            opposing_claim_count=0,
            contradiction_cycle_count=1,
        )
        assert 0.0 <= eff <= raw


class TestRisk:
    def test_risk_floor_applies(self):
        risk = compute_epistemic_risk(0.0, 0, 10, 0.0, 0.0, risk_floor=0.08)
        assert risk == 0.08

    def test_risk_bounded_by_one(self):
        risk = compute_epistemic_risk(1.0, 100, 1, 1.0, 1.0)
        assert risk == 1.0

    def test_contradictions_raise_risk(self):
        low = compute_epistemic_risk(0.3, 0, 10, 0.2, 0.1)
        high = compute_epistemic_risk(0.3, 5, 10, 0.2, 0.1)
        assert high > low


class TestNovelty:
    def test_resolution_score_ratio(self):
        assert compute_contradiction_resolution_score(4, 2) == 0.5
        # No contradictions at all counts as fully resolved
        assert compute_contradiction_resolution_score(0, 0) == 1.0

    def test_gap_coverage_ratio(self):
        assert compute_knowledge_gap_coverage(4, 1) == 0.25

    def test_novelty_bounds(self):
        low = compute_novelty_score(0.0, 0.0, 1.0, 0.0)
        high = compute_novelty_score(1.0, 1.0, 0.0, 1.0)
        assert 0.0 <= low <= high <= 1.0

    def test_interpretation_labels(self):
        assert isinstance(interpret_novelty(0.9), str)
        assert interpret_novelty(0.9) != interpret_novelty(0.1)


class TestTermination:
    def _checker(self, **kw):
        defaults = dict(
            min_iterations=1, max_iterations=10, budget_cap_usd=5.0,
            risk_threshold=0.25, novelty_plateau_delta=0.03,
            novelty_plateau_window=3, stale_iteration_window=2,
        )
        defaults.update(kw)
        return TerminationChecker(**defaults)

    def test_budget_cap_stops_immediately(self):
        checker = self._checker(budget_cap_usd=1.0)
        checker.record_iteration(0.9, 0.1, 5, iteration_cost_usd=2.0)
        stop, reason = checker.should_terminate(1)
        assert stop and "Budget" in reason

    def test_min_iterations_blocks_early_convergence(self):
        checker = self._checker(min_iterations=3)
        checker.record_iteration(0.1, 0.5, 0)
        checker.record_iteration(0.1, 0.5, 0)
        stop, _ = checker.should_terminate(2)
        assert not stop

    def test_risk_convergence_with_stale_claims(self):
        checker = self._checker()
        checker.record_iteration(0.1, 0.9, 0)
        checker.record_iteration(0.1, 0.5, 0)
        stop, reason = checker.should_terminate(2)
        assert stop and "converged" in reason

    def test_novelty_plateau(self):
        checker = self._checker()
        for _ in range(3):
            checker.record_iteration(0.9, 0.50, 3)
        stop, reason = checker.should_terminate(3)
        assert stop and "plateau" in reason.lower()

    def test_no_stop_while_progressing(self):
        checker = self._checker()
        checker.record_iteration(0.9, 0.2, 4)
        checker.record_iteration(0.8, 0.4, 3)
        stop, _ = checker.should_terminate(2)
        assert not stop
