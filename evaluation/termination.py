"""
Termination Conditions
======================
Loop must stop when any of these conditions are met:

1. EpistemicRisk < 0.25 AND no new high-confidence claims in last 2 iterations
2. NoveltyScore plateau (delta < 0.03 over 3 iterations)
3. Budget cap exceeded
"""

from typing import List, Optional, Tuple


class TerminationChecker:
    """Evaluates termination conditions for the research loop."""

    def __init__(
        self,
        min_iterations: int = 3,
        max_iterations: int = 10,
        budget_cap_usd: float = 5.0,
        risk_threshold: float = 0.25,
        novelty_plateau_delta: float = 0.03,
        novelty_plateau_window: int = 3,
        stale_iteration_window: int = 2,
    ):
        self.min_iterations = min_iterations
        self.max_iterations = max_iterations
        self.budget_cap_usd = budget_cap_usd
        self.risk_threshold = risk_threshold
        self.novelty_plateau_delta = novelty_plateau_delta
        self.novelty_plateau_window = novelty_plateau_window
        self.stale_iteration_window = stale_iteration_window

        # History tracking
        self.risk_history: List[float] = []
        self.novelty_history: List[float] = []
        self.new_claims_history: List[int] = []
        self.budget_used: float = 0.0

    def record_iteration(
        self,
        epistemic_risk: float,
        novelty_score: float,
        new_high_confidence_claims: int,
        iteration_cost_usd: float = 0.0,
    ) -> None:
        """Record metrics from a completed iteration."""
        self.risk_history.append(epistemic_risk)
        self.novelty_history.append(novelty_score)
        self.new_claims_history.append(new_high_confidence_claims)
        self.budget_used += iteration_cost_usd

    def should_terminate(self, current_iteration: int) -> Tuple[bool, str]:
        """
        Check all termination conditions.

        Returns:
            (should_stop, reason) tuple.
        """
        # Condition 4: Budget cap exceeded
        if self.budget_used >= self.budget_cap_usd:
            return True, (
                f"Budget cap exceeded "
                f"(${self.budget_used:.2f} >= ${self.budget_cap_usd:.2f})"
            )

        # Minimum iteration enforcement for convergence/plateau checks
        if current_iteration < self.min_iterations:
            return False, (
                f"Continuing research loop "
                f"(min_iterations={self.min_iterations} not met)"
            )

        # Condition 1: Low risk + no new claims
        if self._check_risk_convergence():
            return True, (
                f"Research converged: EpistemicRisk < {self.risk_threshold} "
                f"and no new high-confidence claims in last "
                f"{self.stale_iteration_window} iterations"
            )

        # Condition 2: Novelty plateau
        if self._check_novelty_plateau():
            return True, (
                f"Novelty plateau: delta < {self.novelty_plateau_delta} "
                f"over last {self.novelty_plateau_window} iterations"
            )

        return False, "Continuing research loop"

    def _check_risk_convergence(self) -> bool:
        """
        Condition 1:
        EpistemicRisk < 0.25 AND
        No new high-confidence claims in last 2 iterations
        """
        if len(self.risk_history) < self.stale_iteration_window:
            return False

        # Check if recent risk is below threshold
        recent_risk = self.risk_history[-1]
        if recent_risk >= self.risk_threshold:
            return False

        # Check if no new high-confidence claims in last N iterations
        recent_claims = self.new_claims_history[-self.stale_iteration_window:]
        return all(c == 0 for c in recent_claims)

    def _check_novelty_plateau(self) -> bool:
        """
        Condition 2:
        NoveltyScore plateau (delta < 0.03 over 3 iterations)
        """
        if len(self.novelty_history) < self.novelty_plateau_window:
            return False

        recent = self.novelty_history[-self.novelty_plateau_window:]
        max_delta = max(recent) - min(recent)
        return max_delta < self.novelty_plateau_delta

    def get_status(self) -> dict:
        """Get current termination checker status."""
        return {
            "iterations_completed": len(self.risk_history),
            "min_iterations": self.min_iterations,
            "max_iterations": self.max_iterations,
            "budget_used_usd": round(self.budget_used, 4),
            "budget_cap_usd": self.budget_cap_usd,
            "latest_risk": self.risk_history[-1] if self.risk_history else None,
            "latest_novelty": self.novelty_history[-1] if self.novelty_history else None,
            "risk_threshold": self.risk_threshold,
            "converging": self._check_risk_convergence(),
            "novelty_plateau": self._check_novelty_plateau(),
        }
