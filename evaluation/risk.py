"""
Epistemic Risk Scoring
======================
Implements:
  EpistemicRisk =
    (0.35 × average_uncertainty) +
    (0.30 × (unresolved_contradictions / total_claims)) +
    (0.20 × normalized_gap_severity) +
    (0.15 × source_credibility_variance)
"""


def compute_epistemic_risk(
    average_uncertainty: float,
    unresolved_contradictions: int,
    total_claims: int,
    normalized_gap_severity: float,
    source_credibility_variance: float,
    risk_floor: float = 0.08,
) -> float:
    """
    Compute the Epistemic Risk score.

    Args:
        average_uncertainty: Average (1 - confidence) across all claims.
        unresolved_contradictions: Number of unresolved contradictions.
        total_claims: Total number of claims.
        normalized_gap_severity: Average severity of unresolved knowledge gaps (0-1).
        source_credibility_variance: Variance of source credibility scores.
        risk_floor: Minimum risk floor (finite exploration -> finite risk).

    Returns:
        Epistemic risk score in [risk_floor, 1].
    """
    # Avoid division by zero
    contradiction_ratio = (
        unresolved_contradictions / total_claims if total_claims > 0 else 1.0
    )

    risk = (
        (0.35 * average_uncertainty)
        + (0.30 * contradiction_ratio)
        + (0.20 * normalized_gap_severity)
        + (0.15 * source_credibility_variance)
    )

    risk = max(risk_floor, risk)

    # Clamp to [0, 1]
    return round(max(0.0, min(1.0, risk)), 6)


def compute_average_uncertainty(claims) -> float:
    """
    Compute average uncertainty across all claims.
    Uncertainty = 1 - confidence_estimate
    """
    if not claims:
        return 1.0
    uncertainties = [1.0 - c.confidence_estimate for c in claims]
    return sum(uncertainties) / len(uncertainties)
