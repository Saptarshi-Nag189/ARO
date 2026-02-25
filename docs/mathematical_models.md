# Mathematical Models

All three scoring formulas are implemented exactly as specified and computed at every iteration.

## 1. Hypothesis Confidence

Measures the evidence balance for a hypothesis.

```
SupportScore = Σ (confidence_i × credibility_weight_i)  for supporting claims
OppositionScore = Σ (confidence_i × credibility_weight_i)  for opposing claims

HypothesisConfidence = SupportScore / (SupportScore + OppositionScore + ε)
```

- **ε** = 1e-8 (avoids division by zero)
- Range: [0, 1]
- Computed per hypothesis, then averaged across all hypotheses

**Implementation**: `evaluation/confidence.py`

---

## 2. Epistemic Risk

Measures the overall uncertainty and reliability of the research state.

```
EpistemicRisk =
    (0.35 × average_uncertainty) +
    (0.30 × (unresolved_contradictions / total_claims)) +
    (0.20 × normalized_gap_severity) +
    (0.15 × source_credibility_variance)
```

| Component | Weight | Description |
|-----------|--------|-------------|
| average_uncertainty | 0.35 | Mean of (1 - confidence) across all claims |
| contradiction_ratio | 0.30 | Unresolved contradictions / total claims |
| gap_severity | 0.20 | Average severity of unresolved knowledge gaps |
| credibility_variance | 0.15 | Variance of source credibility scores |

- Range: [0, 1] (clamped)
- Lower is better; < 0.25 triggers convergence check

**Implementation**: `evaluation/risk.py`

---

## 3. Novelty Score

Measures how novel the research findings and proposals are.

```
Novelty =
    0.30 × GraphBridgeScore +
    0.25 × ContradictionResolutionScore +
    0.30 × (1 - PriorArtSimilarity) +
    0.15 × KnowledgeGapCoverage
```

| Component | Weight | Description |
|-----------|--------|-------------|
| GraphBridgeScore | 0.30 | Ratio of bridge nodes in the hypothesis graph |
| ContradictionResolutionScore | 0.25 | Resolved / total contradictions |
| PriorArtSimilarity | 0.30 | Distance from prior art (inverted) |
| KnowledgeGapCoverage | 0.15 | Addressed / total knowledge gaps |

### Interpretation Thresholds

| Score | Interpretation |
|-------|---------------|
| > 0.75 | **Potentially patent-grade** |
| 0.60–0.75 | Incremental improvement |
| < 0.60 | Derivative work |

**Implementation**: `evaluation/novelty.py`

---

## 4. Termination Conditions

| # | Condition | Threshold |
|---|-----------|-----------|
| 1 | Risk converged + stale | Risk < 0.25 AND no new high-confidence claims in 2 iterations |
| 2 | Novelty plateau | Delta < 0.03 over 3 iterations |
| 3 | Max iterations | Configurable (default: 10) |
| 4 | Budget cap | Configurable (default: $5.00) |

**Implementation**: `evaluation/termination.py`
