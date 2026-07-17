"""Skeptic credibility challenges (old finding 3.4): target_id may be a
claim ID or a source ID, and both paths must actually apply."""

from graph import prompts
from graph.nodes import ResearchNodes
from schemas.agent_io import CredibilityChallenge, SkepticOutput, SynthesisOutput
from schemas.claims import Claim
from schemas.sources import Source


def _setup(services):
    nodes = ResearchNodes(services)
    mem = services.memory
    src = mem.add_source(Source(
        title="Paper A", url="https://x.org/a", credibility_score=0.8))
    claim = mem.add_claim(Claim(
        subject="s", relation="r", object="o", source_id=src.id,
        confidence_estimate=0.9, credibility_weight=0.8))
    return nodes, mem, src, claim


def _state(challenge):
    return {
        "skeptic_output": SkepticOutput(
            credibility_challenges=[challenge],
            overall_assessment="ok",
        ),
        "synthesis_output": SynthesisOutput(hypotheses=[], narrative_summary="n"),
        "iteration": 1,
    }


def test_challenge_with_source_id_lowers_source_credibility(services):
    nodes, mem, src, _claim = _setup(services)
    nodes.integrate(_state(CredibilityChallenge(
        target_id=src.id, reason="blog spam", suggested_adjustment=-0.3)))
    assert abs(mem.get_source(src.id).credibility_score - 0.5) < 1e-6


def test_challenge_with_claim_id_lowers_claim_weight(services):
    nodes, mem, _src, claim = _setup(services)
    nodes.integrate(_state(CredibilityChallenge(
        target_id=claim.id, reason="unverifiable", suggested_adjustment=-0.3)))
    assert abs(mem.get_claim(claim.id).credibility_weight - 0.5) < 1e-6


def test_challenge_with_unknown_id_is_dropped_silently(services):
    nodes, mem, src, claim = _setup(services)
    nodes.integrate(_state(CredibilityChallenge(
        target_id="claim_nonexistent", reason="x", suggested_adjustment=-0.5)))
    # Nothing changed
    assert abs(mem.get_source(src.id).credibility_score - 0.8) < 1e-6
    assert abs(mem.get_claim(claim.id).credibility_weight - 0.8) < 1e-6


def test_skeptic_prompt_lists_sources(services):
    _nodes, mem, src, claim = _setup(services)
    prompt = prompts.build_skeptic_prompt(
        [claim], [], sources=mem.get_all_sources())
    assert src.id in prompt
    assert "Paper A" in prompt
    assert claim.id in prompt
