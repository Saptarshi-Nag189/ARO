"""Orchestrator logic that doesn't need an LLM: guardrails, scoring wiring,
contradiction bookkeeping, conclusion fallback."""

from types import SimpleNamespace

import pytest

from agents.orchestrator import Orchestrator
from schemas.agent_io import (
    ClaimExtractionOutput,
    ContradictionResolution,
    Contradiction,
    SkepticOutput,
    SynthesisOutput,
)
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.sources import Source


def _bare_orchestrator(**attrs):
    """Orchestrator without __init__ (no agents/gateway needed)."""
    orch = Orchestrator.__new__(Orchestrator)
    for k, v in attrs.items():
        setattr(orch, k, v)
    return orch


def _claim(subject, source_id="src_1", claim_id=None):
    c = Claim(subject=subject, relation="r", object="o", source_id=source_id,
              confidence_estimate=0.9, credibility_weight=0.8)
    c.id = claim_id
    return c


class FakeMemory:
    def __init__(self):
        self.claims = []
        self.hypotheses = []
        self.resolved_gaps = []
        self.known_gap_ids = set()

    def add_claim(self, c):
        self.claims.append(c)
        return c

    def add_hypothesis(self, h):
        self.hypotheses.append(h)
        return h

    def get_hypothesis(self, hid):
        return None

    def update_hypothesis(self, h):
        return h

    def resolve_knowledge_gap(self, gid):
        if gid in self.known_gap_ids:
            self.resolved_gaps.append(gid)
            return True
        return False


# ─── Persistence guardrails (finding 2.12) ───────────────────────────────


def test_claims_with_unknown_source_are_dropped_not_reattributed():
    orch = _bare_orchestrator(memory=FakeMemory())
    src = Source(id="src_1", title="T", credibility_score=0.8)
    good = _claim("good", source_id="src_1")
    bad = _claim("bad", source_id="src_UNKNOWN")

    persisted = orch._persist_claims(
        ClaimExtractionOutput(claims=[good, bad]), [src])

    assert [c.subject for c in persisted] == ["good"]
    assert bad.source_id == "src_UNKNOWN"  # untouched, not rewritten


def test_hypotheses_without_valid_support_are_dropped():
    mem = FakeMemory()
    orch = _bare_orchestrator(memory=mem)
    known = _claim("known", claim_id="claim_1")

    ok = Hypothesis(statement="ok", supporting_claim_ids=["claim_1"])
    fabricated = Hypothesis(statement="bad", supporting_claim_ids=["claim_MISSING"])

    orch._persist_hypotheses(
        SynthesisOutput(hypotheses=[ok, fabricated], narrative_summary="s"),
        [known],
    )
    assert [h.statement for h in mem.hypotheses] == ["ok"]


# ─── Contradiction bookkeeping (finding 2.5) ─────────────────────────────


def _skeptic_output(pairs):
    return SkepticOutput(
        contradictions=[
            Contradiction(claim_id_a=a, claim_id_b=b, description="d",
                          severity=0.7)
            for a, b in pairs
        ],
        overall_assessment="ok",
    )


def test_contradictions_counted_once_across_iterations():
    orch = _bare_orchestrator(
        memory=FakeMemory(), total_contradictions=0,
        skeptic_detected_gap_count=0,
        seen_contradiction_pairs=set(), open_contradiction_pairs=set(),
    )
    orch._process_skeptic_output(_skeptic_output([("c1", "c2"), ("c2", "c1")]))
    assert orch.total_contradictions == 1  # (a,b) == (b,a)

    # Skeptic re-reports the same pair next iteration → still 1
    orch._process_skeptic_output(_skeptic_output([("c1", "c2")]))
    assert orch.total_contradictions == 1
    assert orch.open_contradiction_pairs == {frozenset(("c1", "c2"))}


def test_synthesis_resolves_only_open_pairs_and_known_gaps():
    mem = FakeMemory()
    mem.known_gap_ids = {"gap_real"}
    orch = _bare_orchestrator(
        memory=mem, resolved_contradictions=0,
        open_contradiction_pairs={frozenset(("c1", "c2"))},
    )
    out = SynthesisOutput(
        hypotheses=[Hypothesis(statement="s", supporting_claim_ids=["c1"])],
        narrative_summary="n",
        resolved_contradictions=[
            ContradictionResolution(claim_id_a="c2", claim_id_b="c1",
                                    resolution="newer data prevails"),
            # Not open — must be ignored (model can't inflate the score)
            ContradictionResolution(claim_id_a="x", claim_id_b="y",
                                    resolution="hallucinated"),
        ],
        resolved_gap_ids=["gap_real", "gap_hallucinated"],
    )
    orch._process_synthesis_resolutions(out)

    assert orch.resolved_contradictions == 1
    assert orch.open_contradiction_pairs == set()
    assert mem.resolved_gaps == ["gap_real"]


# ─── Novelty cap (finding 2.4) ───────────────────────────────────────────


def test_novelty_cap_lifts_when_innovations_exist():
    class NoveltyMemory:
        def get_graph_bridge_score(self):
            return 1.0

        def get_all_knowledge_gaps(self):
            return []

    orch = _bare_orchestrator(
        memory=NoveltyMemory(), total_contradictions=0,
        resolved_contradictions=0,
    )
    capped = orch._compute_novelty(prior_art_similarity=0.1, has_innovations=False)
    uncapped = orch._compute_novelty(prior_art_similarity=0.1, has_innovations=True)
    assert capped == 0.5
    assert uncapped > 0.75  # patent-grade must be reachable


# ─── Conclusion fallback (finding 2.2) ───────────────────────────────────


class FailingGateway:
    def call_text(self, **kwargs):
        raise RuntimeError("simulated LLM failure")


def test_conclusion_fallback_formats_risk():
    orch = _bare_orchestrator(gateway=FailingGateway())
    hyp = SimpleNamespace(statement="X causes Y", confidence=0.8,
                          status="supported", supporting_claim_ids=["c1"],
                          opposing_claim_ids=[])
    metrics = SimpleNamespace(epistemic_risk=0.3, hypothesis_confidence=0.7)
    out = orch._generate_conclusion("q?", [hyp], [], [], metrics)
    assert "30.0%" in out


def test_conclusion_fallback_without_metrics():
    orch = _bare_orchestrator(gateway=FailingGateway())
    hyp = SimpleNamespace(statement="X", confidence=0.8, status="supported",
                          supporting_claim_ids=["c1"], opposing_claim_ids=[])
    out = orch._generate_conclusion("q?", [hyp], [], [], None)
    assert "unknown" in out


def test_conclusion_fallback_without_hypotheses():
    orch = _bare_orchestrator(gateway=FailingGateway())
    out = orch._generate_conclusion("q?", [], [], [], None)
    assert "Insufficient evidence" in out
