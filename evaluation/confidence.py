"""
Hypothesis Confidence Scoring
==============================
Implements:
  SupportScore = sum(confidence × credibility_weight of supporting claims)
  OppositionScore = sum(confidence × credibility_weight of opposing claims)
  HypothesisConfidence = SupportScore / (SupportScore + OppositionScore + epsilon)
"""

from typing import List

from schemas.claims import Claim
from schemas.hypotheses import Hypothesis


def compute_support_score(supporting_claims: List[Claim]) -> float:
    """
    SupportScore = sum(confidence × credibility_weight) for supporting claims.
    """
    return sum(
        c.confidence_estimate * c.credibility_weight
        for c in supporting_claims
    )


def compute_opposition_score(opposing_claims: List[Claim]) -> float:
    """
    OppositionScore = sum(confidence × credibility_weight) for opposing claims.
    """
    return sum(
        c.confidence_estimate * c.credibility_weight
        for c in opposing_claims
    )


def compute_hypothesis_confidence(
    supporting_claims: List[Claim],
    opposing_claims: List[Claim],
    epsilon: float = 1e-8,
) -> float:
    """
    Raw HypothesisConfidence =
        SupportScore / (SupportScore + OppositionScore + epsilon)

    Args:
        supporting_claims: Claims supporting the hypothesis.
        opposing_claims: Claims opposing the hypothesis.
        epsilon: Small constant to avoid division by zero.

    Returns:
        Raw confidence score in [0, 1].
    """
    support = compute_support_score(supporting_claims)
    opposition = compute_opposition_score(opposing_claims)
    confidence = support / (support + opposition + epsilon)
    return round(confidence, 6)

def compute_effective_confidence(
    raw_confidence: float,
    epistemic_risk: float,
    supporting_claim_count: int,
    opposing_claim_count: int,
    contradiction_cycle_count: int,
) -> float:
    """
    Compute Effective Confidence bounded by epistemology rules.
    """
    effective = raw_confidence * (1.0 - epistemic_risk)

    if supporting_claim_count < 2:
        effective = min(effective, 0.85)

    if opposing_claim_count == 0:
        effective = effective * 0.95

    if effective > 0.95:
        if supporting_claim_count < 2 or contradiction_cycle_count == 0:
            effective = 0.95

    return round(effective, 6)


def compute_average_hypothesis_confidence(
    hypotheses_with_claims: List[dict],
    epsilon: float = 1e-8,
) -> float:
    """
    Compute the average confidence across all hypotheses.

    Args:
        hypotheses_with_claims: List of dicts with keys:
            - 'supporting': List[Claim]
            - 'opposing': List[Claim]
        epsilon: Small constant for stability.

    Returns:
        Average confidence in [0, 1].
    """
    if not hypotheses_with_claims:
        return 0.0

    confidences = [
        compute_hypothesis_confidence(
            h["supporting"], h["opposing"], epsilon
        )
        for h in hypotheses_with_claims
    ]
    return round(sum(confidences) / len(confidences), 6)
