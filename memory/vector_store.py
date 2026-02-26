"""
Vector Store — Cross-Session Semantic Memory
=============================================
Uses ChromaDB (embedded) for semantic search across all past sessions.

Architecture:
  - Persists to disk at config.vector_store_path
  - Two collections: "claims" and "hypotheses"
  - ChromaDB uses all-MiniLM-L6-v2 for embeddings (local, no API call)
  - Query latency: <10ms for 100K vectors

ON WRITE:
  When a claim or hypothesis is persisted via MemoryService, it is also
  indexed here for cross-session retrieval.

ON READ:
  Before each research iteration, the orchestrator queries for relevant
  prior findings from ALL past sessions (excluding current).
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("aro.vector_store")


class VectorStore:
    """Cross-session semantic memory using ChromaDB."""

    def __init__(self, persist_dir: str = "./vector_store"):
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path=persist_dir)
            self.claims = self.client.get_or_create_collection(
                "claims",
                metadata={"hnsw:space": "cosine"},
            )
            self.hypotheses = self.client.get_or_create_collection(
                "hypotheses",
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info(
                "VectorStore initialized at %s (claims: %d, hypotheses: %d)",
                persist_dir,
                self.claims.count(),
                self.hypotheses.count(),
            )
        except ImportError:
            logger.warning(
                "chromadb not installed — vector store disabled. "
                "Install with: pip install chromadb"
            )
            self._available = False
            self.client = None
            self.claims = None
            self.hypotheses = None
        except Exception as e:
            logger.error("VectorStore init failed: %s", e)
            self._available = False
            self.client = None
            self.claims = None
            self.hypotheses = None

    @property
    def available(self) -> bool:
        return self._available

    # ─── Indexing ─────────────────────────────────────────────────────────

    def index_claim(
        self,
        claim_id: str,
        text: str,
        session_id: str,
        confidence: float = 0.5,
        source_type: str = "web",
    ) -> None:
        """Index a claim for cross-session retrieval."""
        if not self._available:
            return
        try:
            self.claims.upsert(
                ids=[claim_id],
                documents=[text],
                metadatas=[{
                    "session_id": session_id,
                    "confidence": confidence,
                    "source_type": source_type,
                }],
            )
        except Exception as e:
            logger.warning("Failed to index claim %s: %s", claim_id, e)

    def index_hypothesis(
        self,
        hyp_id: str,
        statement: str,
        session_id: str,
        confidence: float = 0.5,
    ) -> None:
        """Index a hypothesis for cross-session retrieval."""
        if not self._available:
            return
        try:
            self.hypotheses.upsert(
                ids=[hyp_id],
                documents=[statement],
                metadatas=[{
                    "session_id": session_id,
                    "confidence": confidence,
                }],
            )
        except Exception as e:
            logger.warning("Failed to index hypothesis %s: %s", hyp_id, e)

    # ─── Retrieval ────────────────────────────────────────────────────────

    def search_prior_claims(
        self,
        query: str,
        top_k: int = 10,
        exclude_session: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[Dict]:
        """
        Find semantically similar claims from past sessions.

        Returns list of dicts: {id, text, distance, metadata}
        """
        if not self._available or self.claims.count() == 0:
            return []
        try:
            where = None
            if exclude_session:
                where = {"session_id": {"$ne": exclude_session}}

            results = self.claims.query(
                query_texts=[query],
                n_results=min(top_k, self.claims.count()),
                where=where,
            )
            return self._format_results(results, min_confidence)
        except Exception as e:
            logger.warning("Claim search failed: %s", e)
            return []

    def search_prior_hypotheses(
        self,
        query: str,
        top_k: int = 5,
        exclude_session: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[Dict]:
        """Find semantically similar hypotheses from past sessions."""
        if not self._available or self.hypotheses.count() == 0:
            return []
        try:
            where = None
            if exclude_session:
                where = {"session_id": {"$ne": exclude_session}}

            results = self.hypotheses.query(
                query_texts=[query],
                n_results=min(top_k, self.hypotheses.count()),
                where=where,
            )
            return self._format_results(results, min_confidence)
        except Exception as e:
            logger.warning("Hypothesis search failed: %s", e)
            return []

    # ─── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get vector store stats for health check."""
        if not self._available:
            return {"available": False, "claims": 0, "hypotheses": 0}
        return {
            "available": True,
            "claims": self.claims.count(),
            "hypotheses": self.hypotheses.count(),
        }

    # ─── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _format_results(
        raw_results: dict,
        min_confidence: float = 0.0,
    ) -> List[Dict]:
        """Convert ChromaDB query results to flat list of dicts."""
        formatted = []
        if not raw_results or not raw_results.get("ids"):
            return formatted

        ids = raw_results["ids"][0]
        docs = raw_results["documents"][0]
        distances = raw_results.get("distances", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]

        for i, doc_id in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            conf = meta.get("confidence", 0.0)
            if conf < min_confidence:
                continue
            formatted.append({
                "id": doc_id,
                "text": docs[i],
                "distance": distances[i] if i < len(distances) else None,
                "session_id": meta.get("session_id", ""),
                "confidence": conf,
                "source_type": meta.get("source_type", ""),
            })
        return formatted
