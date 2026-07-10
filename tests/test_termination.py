"""TerminationChecker — the deterministic loop-exit logic."""

from evaluation.termination import TerminationChecker


def _iterate(tc, risk=0.9, novelty_seq=None, claims=3, n=20):
    """Drive the checker until it stops; return (iteration, reason)."""
    for i in range(1, n + 1):
        novelty = novelty_seq[i - 1] if novelty_seq else 0.05 * i % 1.0
        tc.record_iteration(
            epistemic_risk=risk,
            novelty_score=novelty,
            new_high_confidence_claims=claims,
        )
        stop, reason = tc.should_terminate(i)
        if stop:
            return i, reason
    return None, "never"


def test_max_iterations_is_enforced():
    tc = TerminationChecker(min_iterations=3, max_iterations=5)
    # Diverging novelty so the plateau check never fires
    i, reason = _iterate(tc, novelty_seq=[0.1, 0.9, 0.1, 0.9, 0.1, 0.9] * 4)
    assert i == 5
    assert "Maximum iterations" in reason


def test_max_iterations_wins_over_min_iterations():
    tc = TerminationChecker(min_iterations=3, max_iterations=1)
    stop, reason = tc.should_terminate(1)
    assert stop and "Maximum iterations" in reason


def test_min_iterations_blocks_early_convergence():
    tc = TerminationChecker(min_iterations=3, max_iterations=10)
    tc.record_iteration(epistemic_risk=0.1, novelty_score=0.5,
                        new_high_confidence_claims=0)
    stop, _ = tc.should_terminate(1)
    assert not stop


def test_risk_convergence():
    tc = TerminationChecker(min_iterations=3, max_iterations=10,
                            risk_threshold=0.25, stale_iteration_window=2)
    for i in range(1, 4):
        tc.record_iteration(epistemic_risk=0.1, novelty_score=0.1 * i,
                            new_high_confidence_claims=0)
    stop, reason = tc.should_terminate(3)
    assert stop and "converged" in reason


def test_novelty_plateau():
    tc = TerminationChecker(min_iterations=3, max_iterations=10,
                            novelty_plateau_delta=0.03,
                            novelty_plateau_window=3)
    for i in range(1, 4):
        tc.record_iteration(epistemic_risk=0.9, novelty_score=0.500 + i * 0.001,
                            new_high_confidence_claims=5)
    stop, reason = tc.should_terminate(3)
    assert stop and "plateau" in reason


def test_budget_cap():
    tc = TerminationChecker(min_iterations=3, max_iterations=10,
                            budget_cap_usd=1.0)
    tc.record_iteration(epistemic_risk=0.9, novelty_score=0.1,
                        new_high_confidence_claims=5, iteration_cost_usd=1.5)
    stop, reason = tc.should_terminate(1)
    assert stop and "Budget" in reason
