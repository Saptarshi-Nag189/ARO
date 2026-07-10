"""
Prior Art Tool
==============
Prior-art scan tool for Innovation mode.
GUARDRAIL: No innovation without prior-art scan.

Scans real scholarly sources (Semantic Scholar + OpenAlex — both free,
no API keys) and estimates prior-art similarity from lexical overlap
between the research objective/hypotheses and the retrieved abstracts.
The similarity estimate is a heuristic: it exists to give the novelty
score a real, evidence-linked input rather than a constant.
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger("aro.tools.prior_art")

# Similarity estimate is clamped to this range: a scan that finds nothing
# still doesn't prove novelty (floor), and lexical overlap alone can't
# prove full anticipation (ceiling).
_SIMILARITY_FLOOR = 0.15
_SIMILARITY_CEILING = 0.90
_DEFAULT_SIMILARITY = 0.5

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "have", "has", "been", "will", "would", "could", "should",
    "into", "onto", "about", "these", "those", "their", "them", "they",
    "what", "which", "when", "where", "how", "why", "can", "may", "might",
    "using", "based", "novel", "approach", "approaches", "method",
    "methods", "study", "studies", "research", "paper", "results",
}


def _tokens(text: str) -> set:
    """Meaningful lowercase tokens (>3 chars, non-stopword)."""
    return {
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) > 3 and w not in _STOPWORDS
    }


def _overlap_coefficient(a: set, b: set) -> float:
    """|A ∩ B| / min(|A|, |B|) — robust when the two texts differ in length."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class PriorArtResult:
    """A prior art reference."""

    def __init__(
        self,
        title: str,
        description: str,
        similarity_score: float,
        source: str,
        url: str = "",
    ):
        self.title = title
        self.description = description
        self.similarity_score = similarity_score  # 0-1
        self.source = source
        self.url = url

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "similarity_score": self.similarity_score,
            "source": self.source,
            "url": self.url,
        }


class PriorArtTool:
    """
    Prior art scanning tool.
    Queries Semantic Scholar and OpenAlex for work related to the research
    objective, scores each hit's lexical overlap against the objective +
    hypotheses, and returns references plus an estimated similarity.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def scan(
        self,
        research_objective: str,
        hypotheses_summary: str,
        max_results: int = 10,
    ) -> dict:
        """
        Perform a prior-art scan against real scholarly sources.

        Returns a dict with prior_art_references (scored hits) and
        estimated_prior_art_similarity in [0, 1]. Falls back to a neutral
        default (0.5, no references) if all searches fail, so innovation
        mode keeps working offline.
        """
        logger.info("Prior art scan for: %s", research_objective[:100])

        hits = self._search_scholarly_sources(research_objective, max_results)

        query_tokens = _tokens(f"{research_objective} {hypotheses_summary}")
        references: List[PriorArtResult] = []
        for hit in hits:
            hit_tokens = _tokens(f"{hit.get('title', '')} {hit.get('snippet', '')}")
            score = _overlap_coefficient(query_tokens, hit_tokens)
            references.append(PriorArtResult(
                title=hit.get("title", "Untitled"),
                description=(hit.get("snippet") or "")[:300],
                similarity_score=round(score, 4),
                source=hit.get("source_type", "academic"),
                url=hit.get("url", ""),
            ))

        references.sort(key=lambda r: r.similarity_score, reverse=True)
        references = references[:max_results]

        if references:
            # Average of the top-3 most similar hits: one near-identical
            # paper matters more than many loosely related ones.
            top = [r.similarity_score for r in references[:3]]
            estimated = sum(top) / len(top)
            estimated = min(_SIMILARITY_CEILING, max(_SIMILARITY_FLOOR, estimated))
            scan_completed = True
        else:
            estimated = _DEFAULT_SIMILARITY
            scan_completed = False
            logger.warning(
                "Prior art scan found no results (network issue or empty "
                "corpus) — using neutral similarity %.2f", estimated,
            )

        return {
            "scan_completed": scan_completed,
            "research_objective": research_objective,
            "hypotheses_context": hypotheses_summary,
            "scan_instructions": (
                f"Analyze the prior art references below relative to: "
                f"{research_objective}\n"
                f"Current hypotheses: {hypotheses_summary}\n\n"
                f"For each proposal, differentiate explicitly from the most "
                f"similar references and cite them by title."
            ),
            "prior_art_references": [r.to_dict() for r in references],
            "estimated_prior_art_similarity": round(estimated, 4),
            "similarity_method": (
                "lexical overlap (top-3 mean) against Semantic Scholar + "
                "OpenAlex results" if scan_completed else "default (scan failed)"
            ),
        }

    @staticmethod
    def _search_scholarly_sources(query: str, max_results: int) -> List[dict]:
        """Query the free scholarly engines already used by web research."""
        from tools.web_search import search_semantic_scholar, search_openalex

        hits: List[dict] = []
        per_engine = max(3, max_results // 2)
        for searcher in (search_semantic_scholar, search_openalex):
            try:
                hits.extend(searcher(query, max_results=per_engine))
            except Exception as e:
                logger.warning(
                    "Prior art search via %s failed: %s",
                    getattr(searcher, "__name__", "engine"), e,
                )

        # Deduplicate by URL/title
        seen = set()
        unique = []
        for h in hits:
            key = h.get("url") or h.get("title")
            if key and key not in seen:
                seen.add(key)
                unique.append(h)
        return unique
