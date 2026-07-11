"""MemoryService guardrails, source dedup, claim merges, gap lifecycle."""

import pytest

from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap
from schemas.sources import Source


def _claim(subject="Transformers", relation="outperform", obj="RNNs",
           source_id="src_x", conf=0.9, cred=0.8):
    return Claim(subject=subject, relation=relation, object=obj,
                 source_id=source_id, confidence_estimate=conf,
                 credibility_weight=cred)


# ─── Guardrails ──────────────────────────────────────────────────────────


def test_claim_without_source_is_rejected(memory):
    with pytest.raises(ValueError, match="GUARDRAIL"):
        memory.add_claim(_claim(source_id="src_nonexistent"))


def test_hypothesis_without_claims_is_rejected(memory):
    with pytest.raises(ValueError, match="GUARDRAIL"):
        memory.add_hypothesis(Hypothesis(statement="unsupported"))


def test_hypothesis_with_unknown_claim_is_rejected(memory):
    with pytest.raises(ValueError, match="GUARDRAIL"):
        memory.add_hypothesis(Hypothesis(
            statement="s", supporting_claim_ids=["claim_missing"]))


# ─── Source dedup (finding 2.14) ─────────────────────────────────────────


def test_sources_deduplicate_by_url(memory):
    s1 = memory.add_source(Source(title="Paper A", url="https://x.org/a"))
    s2 = memory.add_source(Source(title="Paper A again", url="https://x.org/a/"))
    assert s1.id == s2.id
    assert memory.source_registry.count_sources() == 1


def test_urlless_sources_deduplicate_by_title(memory):
    s1 = memory.add_source(Source(title="Training knowledge"))
    s2 = memory.add_source(Source(title="Training knowledge"))
    assert s1.id == s2.id


def test_distinct_urls_are_distinct_sources(memory):
    s1 = memory.add_source(Source(title="A", url="https://x.org/a"))
    s2 = memory.add_source(Source(title="B", url="https://x.org/b"))
    assert s1.id != s2.id
    assert memory.source_registry.count_sources() == 2


# ─── Claim merge corroboration (finding 2.14) ────────────────────────────


def test_merge_tracks_corroborating_sources(memory):
    src_a = memory.add_source(Source(title="A", url="https://x.org/a"))
    src_b = memory.add_source(Source(title="B", url="https://x.org/b"))

    first = memory.add_claim(_claim(source_id=src_a.id))
    merged = memory.add_claim(_claim(source_id=src_b.id))

    # Same subject/relation/object → merged into the first claim
    assert merged.id == first.id
    assert merged.evidence_count == 2
    assert src_b.id in merged.corroborating_source_ids

    # And it round-trips through the DB
    reloaded = memory.get_claim(first.id)
    assert src_b.id in reloaded.corroborating_source_ids


def test_merge_same_source_adds_no_corroboration(memory):
    src_a = memory.add_source(Source(title="A", url="https://x.org/a"))
    memory.add_claim(_claim(source_id=src_a.id))
    merged = memory.add_claim(_claim(source_id=src_a.id))
    assert merged.corroborating_source_ids == []


def test_distinct_claims_do_not_merge(memory):
    src = memory.add_source(Source(title="A", url="https://x.org/a"))
    c1 = memory.add_claim(_claim(subject="Transformers", source_id=src.id))
    c2 = memory.add_claim(_claim(subject="Quantum computers", source_id=src.id))
    assert c1.id != c2.id


# ─── Knowledge gap lifecycle (finding 2.5) ───────────────────────────────


def test_gap_resolution_lifecycle(memory):
    gap = memory.add_knowledge_gap(KnowledgeGap(description="missing data"))
    assert len(memory.get_unresolved_gaps()) == 1

    assert memory.resolve_knowledge_gap(gap.id) is True
    assert memory.get_unresolved_gaps() == []
    assert memory.get_all_knowledge_gaps()[0].resolved is True

    # Unknown IDs are rejected, not silently accepted
    assert memory.resolve_knowledge_gap("gap_nonexistent") is False


def test_session_scoping(memory, tmp_path):
    from memory.memory_service import MemoryService
    src = memory.add_source(Source(title="A", url="https://x.org/a"))
    memory.add_claim(_claim(source_id=src.id))

    other = MemoryService(
        db_path=str(tmp_path / "test.db"),
        session_id="session_otherotherot",
        enable_cross_session_memory=False,
    )
    try:
        assert other.get_all_claims() == []
    finally:
        other.close()
