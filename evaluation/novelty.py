"""
Novelty Scoring
===============
Implements:
  Novelty =
    0.30 × GraphBridgeScore +
    0.25 × ContradictionResolutionScore +
    0.30 × (1 - PriorArtSimilarity) +
    0.15 × KnowledgeGapCoverage

Interpretation thresholds:
  > 0.75 = potentially patent-grade
  0.6–0.75 = incremental
  < 0.6 = derivative
"""


def compute_novelty_score(
    graph_bridge_score: float,
    contradiction_resolution_score: float,
    prior_art_similarity: float,
    knowledge_gap_coverage: float,
) -> float:
    """
    Compute the Novelty Score.

    Args:
        graph_bridge_score: Ratio of bridge nodes to total nodes in the
            hypothesis graph. Higher = more novel connections.
        contradiction_resolution_score: Ratio of resolved contradictions
            to total contradictions. Higher = more contradictions resolved.
        prior_art_similarity: Similarity to existing prior art (0-1).
            Lower similarity = higher novelty.
        knowledge_gap_coverage: Ratio of gaps addressed by innovation
            proposals to total gaps.

    Returns:
        Novelty score in [0, 1].
    """
    novelty = (
        (0.30 * graph_bridge_score)
        + (0.25 * contradiction_resolution_score)
        + (0.30 * (1.0 - prior_art_similarity))
        + (0.15 * knowledge_gap_coverage)
    )

    return round(max(0.0, min(1.0, novelty)), 6)


def interpret_novelty(score: float) -> str:
    """
    Interpret a novelty score.

    Returns:
        'patent-grade', 'incremental', or 'derivative'
    """
    if score > 0.75:
        return "patent-grade"
    elif score >= 0.6:
        return "incremental"
    else:
        return "derivative"


def compute_contradiction_resolution_score(
    total_contradictions: int,
    resolved_contradictions: int,
) -> float:
    """
    Compute the contradiction resolution score.
    """
    if total_contradictions == 0:
        return 1.0  # No contradictions = fully resolved
    return resolved_contradictions / total_contradictions


def compute_knowledge_gap_coverage(
    total_gaps: int,
    addressed_gaps: int,
) -> float:
    """
    Compute knowledge gap coverage ratio.
    """
    if total_gaps == 0:
        return 0.0  # If no gaps exist, we didn't address any (prevents inflated novelty)
    return addressed_gaps / total_gaps
