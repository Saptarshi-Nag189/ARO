"""Pure-function scoring layer: confidence, risk, novelty."""

from evaluation.confidence import (
    compute_hypothesis_confidence,
    compute_effective_confidence,
)
from evaluation.risk import compute_epistemic_risk, compute_average_uncertainty
from evaluation.novelty import (
    compute_novelty_score,
    interpret_novelty,
    compute_contradiction_resolution_score,
    compute_knowledge_gap_coverage,
)
from schemas.claims import Claim


def _claim(conf, cred, source="src_1"):
    return Claim(subject="s", relation="r", object="o", source_id=source,
                 confidence_estimate=conf, credibility_weight=cred)


def test_hypothesis_confidence_support_vs_opposition():
    support = [_claim(0.9, 0.9)]
    oppose = [_claim(0.9, 0.9)]
    assert compute_hypothesis_confidence(support, []) > 0.99
    assert abs(compute_hypothesis_confidence(support, oppose) - 0.5) < 0.01
    assert compute_hypothesis_confidence([], oppose) == 0.0


def test_effective_confidence_caps():
    # Single supporting claim capped at 0.85
    eff = compute_effective_confidence(
        raw_confidence=1.0, epistemic_risk=0.0,
        supporting_claim_count=1, opposing_claim_count=1,
        contradiction_cycle_count=1,
    )
    assert eff <= 0.85
    # Unopposed hypotheses get the 0.95 haircut
    eff = compute_effective_confidence(
        raw_confidence=1.0, epistemic_risk=0.0,
        supporting_claim_count=3, opposing_claim_count=0,
        contradiction_cycle_count=1,
    )
    assert eff <= 0.95


def test_epistemic_risk_floor_and_range():
    risk = compute_epistemic_risk(
        average_uncertainty=0.0, unresolved_contradictions=0,
        total_claims=10, normalized_gap_severity=0.0,
        source_credibility_variance=0.0, risk_floor=0.08,
    )
    assert risk == 0.08
    risk = compute_epistemic_risk(
        average_uncertainty=1.0, unresolved_contradictions=10,
        total_claims=10, normalized_gap_severity=1.0,
        source_credibility_variance=1.0,
    )
    assert risk <= 1.0


def test_average_uncertainty_empty_claims_is_max():
    assert compute_average_uncertainty([]) == 1.0


def test_novelty_composition_and_interpretation():
    assert compute_novelty_score(1.0, 1.0, 0.0, 1.0) == 1.0
    assert compute_novelty_score(0.0, 0.0, 1.0, 0.0) == 0.0
    assert interpret_novelty(0.8) == "patent-grade"
    assert interpret_novelty(0.65) == "incremental"
    assert interpret_novelty(0.3) == "derivative"


def test_contradiction_resolution_score():
    assert compute_contradiction_resolution_score(0, 0) == 1.0
    assert compute_contradiction_resolution_score(4, 1) == 0.25


def test_gap_coverage_no_gaps_is_zero():
    assert compute_knowledge_gap_coverage(0, 0) == 0.0
    assert compute_knowledge_gap_coverage(4, 2) == 0.5
