"""Pipeline behaviors ported from the v2 orchestrator test suite:
persistence guardrails, contradiction bookkeeping, novelty cap,
conclusion fallback — now exercised against the graph nodes."""

from types import SimpleNamespace

from graph.nodes import ResearchNodes
from schemas.agent_io import (
    Contradiction,
    ContradictionResolution,
    SkepticOutput,
    SynthesisOutput,
)
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap
from schemas.sources import Source


def _seed_claim(memory, subject="known"):
    source = memory.add_source(Source(title=f"T-{subject}", credibility_score=0.8))
    claim = memory.add_claim(Claim(
        subject=subject, relation="r", object="o", source_id=source.id,
        confidence_estimate=0.9, credibility_weight=0.8,
    ))
    return claim


def _skeptic(pairs=()):
    return SkepticOutput(
        contradictions=[
            Contradiction(claim_id_a=a, claim_id_b=b, description="d", severity=0.7)
            for a, b in pairs
        ],
        overall_assessment="ok",
    )


def _synthesis(hypotheses=(), resolved=(), resolved_gap_ids=()):
    return SynthesisOutput(
        hypotheses=list(hypotheses),
        narrative_summary="n",
        resolved_contradictions=list(resolved),
        resolved_gap_ids=list(resolved_gap_ids),
    )


# ─── Persistence guardrails (v2 finding 2.12) ────────────────────────────


def test_hypotheses_without_valid_support_are_dropped(services):
    nodes = ResearchNodes(services)
    known = _seed_claim(services.memory)

    ok = Hypothesis(statement="ok", supporting_claim_ids=[known.id])
    fabricated = Hypothesis(statement="bad", supporting_claim_ids=["claim_MISSING"])

    nodes.integrate({
        "skeptic_output": _skeptic(),
        "synthesis_output": _synthesis([ok, fabricated]),
    })

    statements = [h.statement for h in services.memory.get_all_hypotheses()]
    assert statements == ["ok"]


def test_claims_with_unknown_source_are_dropped_not_reattributed(services, monkeypatch):
    from schemas.agent_io import ClaimExtractionOutput, ResearchFinding, ResearchOutput

    nodes = ResearchNodes(services)
    research_output = ResearchOutput(findings=[
        ResearchFinding(content="finding", source_title="Real Source",
                        source_url="https://example.org/x", credibility_estimate=0.8),
    ])

    def fake_run_agent(agent_key, user_message, iteration):
        registered = services.memory.get_all_sources()
        good = Claim(subject="good", relation="r", object="o",
                     source_id=registered[-1].id,
                     confidence_estimate=0.9, credibility_weight=0.8)
        bad = Claim(subject="bad", relation="r", object="o",
                    source_id="src_UNKNOWN",
                    confidence_estimate=0.9, credibility_weight=0.8)
        return ClaimExtractionOutput(claims=[good, bad]), 10, {
            "agent": agent_key, "inputs": "", "outputs": None,
            "tokens": 10, "elapsed": 0.0,
        }

    monkeypatch.setattr(nodes, "_run_agent", fake_run_agent)
    updates = nodes.extract_claims({"research_output": research_output, "iteration": 1})

    persisted_subjects = [
        services.memory.get_claim(cid).subject for cid in updates["new_claim_ids"]
    ]
    assert persisted_subjects == ["good"]


# ─── Contradiction bookkeeping (v2 finding 2.5) ──────────────────────────


def test_contradictions_counted_once_across_iterations(services):
    nodes = ResearchNodes(services)
    state = {
        "skeptic_output": _skeptic([("c1", "c2"), ("c2", "c1")]),
        "synthesis_output": _synthesis(),
    }
    updates = nodes.integrate(state)
    assert updates["total_contradictions"] == 1  # (a,b) == (b,a)

    # Skeptic re-reports the same pair next iteration → still 1
    state2 = {
        "skeptic_output": _skeptic([("c1", "c2")]),
        "synthesis_output": _synthesis(),
        "total_contradictions": updates["total_contradictions"],
        "seen_contradiction_pairs": updates["seen_contradiction_pairs"],
        "open_contradiction_pairs": updates["open_contradiction_pairs"],
    }
    updates2 = nodes.integrate(state2)
    assert updates2["total_contradictions"] == 1
    assert updates2["open_contradiction_pairs"] == [["c1", "c2"]]


def test_synthesis_resolves_only_open_pairs_and_shown_gaps(services):
    nodes = ResearchNodes(services)
    gap = services.memory.add_knowledge_gap(
        KnowledgeGap(description="real gap", severity=0.5)
    )

    updates = nodes.integrate({
        "skeptic_output": _skeptic(),
        "synthesis_output": _synthesis(
            resolved=[
                ContradictionResolution(claim_id_a="c2", claim_id_b="c1",
                                        resolution="newer data prevails"),
                # Not open — must be ignored (model can't inflate the score)
                ContradictionResolution(claim_id_a="x", claim_id_b="y",
                                        resolution="hallucinated"),
            ],
            resolved_gap_ids=[gap.id, "gap_hallucinated"],
        ),
        "open_contradiction_pairs": [["c1", "c2"]],
        "gaps_snapshot": [gap],
    })

    assert updates["resolved_contradictions"] == 1
    assert updates["open_contradiction_pairs"] == []
    resolved = [g for g in services.memory.get_all_knowledge_gaps() if g.resolved]
    assert [g.id for g in resolved] == [gap.id]


# ─── Novelty cap (v2 finding 2.4) ────────────────────────────────────────


def test_novelty_cap_lifts_when_innovations_exist(services, monkeypatch):
    nodes = ResearchNodes(services)
    monkeypatch.setattr(services.memory, "get_graph_bridge_score", lambda: 1.0)

    state = {"total_contradictions": 0, "resolved_contradictions": 0}
    capped = nodes._compute_novelty(state, prior_art_similarity=0.1,
                                    has_innovations=False)
    uncapped = nodes._compute_novelty(state, prior_art_similarity=0.1,
                                      has_innovations=True)
    assert capped == 0.5
    assert uncapped > 0.75  # patent-grade must be reachable


# ─── Conclusion fallback (v2 finding 2.2) ────────────────────────────────


def _fail_invoke_plain(*args, **kwargs):
    raise RuntimeError("simulated LLM failure")


def test_conclusion_fallback_formats_risk(services, monkeypatch):
    import graph.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "invoke_plain", _fail_invoke_plain)

    nodes = ResearchNodes(services)
    hyp = SimpleNamespace(statement="X causes Y", confidence=0.8,
                          status="supported", supporting_claim_ids=["c1"],
                          opposing_claim_ids=[])
    metrics = SimpleNamespace(epistemic_risk=0.3, hypothesis_confidence=0.7)
    out = nodes._generate_conclusion({"objective": "q?"}, [hyp], [], [], metrics)
    assert "30.0%" in out


def test_conclusion_fallback_without_hypotheses(services, monkeypatch):
    import graph.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "invoke_plain", _fail_invoke_plain)

    nodes = ResearchNodes(services)
    out = nodes._generate_conclusion({"objective": "q?"}, [], [], [], None)
    assert "Insufficient evidence" in out
