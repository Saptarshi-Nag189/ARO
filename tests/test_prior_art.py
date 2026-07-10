"""PriorArtTool — real scan wiring with offline mocks (finding 2.11)."""

from unittest.mock import patch

from tools.prior_art_tool import PriorArtTool, _overlap_coefficient, _tokens


def _hits_similar():
    return [
        {"title": "Quantum error correction with surface codes",
         "url": "https://x.org/1",
         "snippet": "surface codes for quantum error correction in qubits",
         "source_type": "academic_paper"},
        {"title": "Unrelated botany paper", "url": "https://x.org/2",
         "snippet": "photosynthesis in alpine flowers",
         "source_type": "academic"},
    ]


def test_scan_scores_and_ranks_references():
    tool = PriorArtTool()
    with patch.object(PriorArtTool, "_search_scholarly_sources",
                      return_value=_hits_similar()):
        result = tool.scan(
            "quantum error correction using surface codes",
            "surface codes reduce logical error rates",
        )

    assert result["scan_completed"] is True
    refs = result["prior_art_references"]
    assert len(refs) == 2
    # The on-topic paper must rank above the botany paper
    assert refs[0]["url"] == "https://x.org/1"
    assert refs[0]["similarity_score"] > refs[1]["similarity_score"]
    # Similarity reflects real overlap, clamped to [0.15, 0.90]
    assert 0.15 <= result["estimated_prior_art_similarity"] <= 0.90


def test_scan_falls_back_to_neutral_default_offline():
    tool = PriorArtTool()
    with patch.object(PriorArtTool, "_search_scholarly_sources",
                      return_value=[]):
        result = tool.scan("anything", "summary")
    assert result["scan_completed"] is False
    assert result["estimated_prior_art_similarity"] == 0.5
    assert result["prior_art_references"] == []


def test_scan_survives_engine_exceptions():
    tool = PriorArtTool()

    def boom(query, max_results=3):
        raise ConnectionError("no network")

    with patch("tools.web_search.search_semantic_scholar", boom), \
         patch("tools.web_search.search_openalex", boom):
        result = tool.scan("anything", "summary")
    assert result["estimated_prior_art_similarity"] == 0.5


def test_overlap_coefficient_behaviour():
    a = _tokens("quantum error correction surface codes")
    assert _overlap_coefficient(a, a) == 1.0
    assert _overlap_coefficient(a, _tokens("alpine photosynthesis")) == 0.0
    assert _overlap_coefficient(a, set()) == 0.0
