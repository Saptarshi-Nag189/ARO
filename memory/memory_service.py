"""
Memory Service (Unified Facade)
================================
All memory mutations go through this service.
No agent writes to DB directly — only through MemoryService.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from memory.db import initialize_database
from memory.claim_store import ClaimStore
from memory.hypothesis_graph import HypothesisGraph
from memory.source_registry import SourceRegistry
from schemas.claims import Claim
from schemas.hypotheses import Hypothesis
from schemas.knowledge_gaps import KnowledgeGap
from schemas.sources import Source


class MemoryService:
    """
    Unified facade for all memory operations.
    Enforces guardrails:
      - No claim insertion without source
      - No hypothesis without supporting claims
    """

    def __init__(self, db_path: str = "aro_memory.db", session_id: Optional[str] = None):
        self.conn = initialize_database(db_path)
        self.session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        self.claim_store = ClaimStore(self.conn, self.session_id)
        self.hypothesis_graph = HypothesisGraph(self.conn, self.session_id)
        self.source_registry = SourceRegistry(self.conn, self.session_id)

    # ─── Session Management ───────────────────────────────────────────────

    def create_session(self, research_objective: str, mode: str = "autonomous") -> str:
        """Create a new research session."""
        self.conn.execute(
            "INSERT INTO sessions (id, research_objective, mode) VALUES (?, ?, ?)",
            (self.session_id, research_objective, mode),
        )
        self.conn.commit()
        return self.session_id

    def update_session_status(self, status: str) -> None:
        """Update session status."""
        self.conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat(), self.session_id),
        )
        self.conn.commit()

    # ─── Source Operations ────────────────────────────────────────────────

    def add_source(self, source: Source) -> Source:
        """Register a new source."""
        return self.source_registry.add_source(source)

    def get_source(self, source_id: str) -> Optional[Source]:
        """Get a source by ID."""
        return self.source_registry.get_source(source_id)

    def get_all_sources(self) -> List[Source]:
        """Get all sources."""
        return self.source_registry.get_all_sources()

    def update_source_credibility(self, source_id: str, new_score: float) -> bool:
        """Update source credibility."""
        return self.source_registry.update_credibility(source_id, new_score)

    # ─── Claim Operations (with guardrails) ───────────────────────────────

    def add_claim(self, claim: Claim) -> Claim:
        """
        Add a claim with guardrail enforcement:
        GUARDRAIL: No claim insertion without source.
        """
        # Verify source exists
        source = self.source_registry.get_source(claim.source_id)
        if source is None:
            raise ValueError(
                f"GUARDRAIL VIOLATION: Cannot add claim without valid source. "
                f"Source '{claim.source_id}' not found. Register the source first."
            )
        return self.claim_store.add_claim(claim)

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get a claim by ID."""
        return self.claim_store.get_claim(claim_id)

    def get_all_claims(self) -> List[Claim]:
        """Get all claims."""
        return self.claim_store.get_all_claims()

    def count_claims(self) -> int:
        """Count total claims."""
        return self.claim_store.count_claims()

    # ─── Hypothesis Operations (with guardrails) ──────────────────────────

    def add_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        """
        Add a hypothesis with guardrail enforcement:
        GUARDRAIL: No hypothesis without supporting claims.
        """
        if not hypothesis.supporting_claim_ids:
            raise ValueError(
                "GUARDRAIL VIOLATION: Cannot add hypothesis without "
                "at least one supporting claim."
            )
        # Verify at least one supporting claim exists
        for claim_id in hypothesis.supporting_claim_ids:
            if self.claim_store.get_claim(claim_id) is None:
                raise ValueError(
                    f"GUARDRAIL VIOLATION: Supporting claim '{claim_id}' "
                    f"not found in database."
                )
        return self.hypothesis_graph.add_hypothesis(hypothesis)

    def update_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        """Update an existing hypothesis."""
        return self.hypothesis_graph.update_hypothesis(hypothesis)

    def get_hypothesis(self, hyp_id: str) -> Optional[Hypothesis]:
        """Get a hypothesis by ID."""
        return self.hypothesis_graph.get_hypothesis(hyp_id)

    def get_all_hypotheses(self) -> List[Hypothesis]:
        """Get all hypotheses."""
        return self.hypothesis_graph.get_all_hypotheses()

    def get_graph_bridge_score(self) -> float:
        """Get the graph bridge score for novelty computation."""
        return self.hypothesis_graph.compute_graph_bridge_score()

    # ─── Knowledge Gap Operations ─────────────────────────────────────────

    def add_knowledge_gap(self, gap: KnowledgeGap) -> KnowledgeGap:
        """Add a knowledge gap."""
        # Ignore model-provided IDs and force an internally generated ID.
        gap.id = f"gap_{uuid.uuid4().hex[:12]}"
        try:
            self.conn.execute(
                """
                INSERT INTO knowledge_gaps (id, session_id, description, severity,
                                            related_hypothesis_ids, suggested_queries,
                                            resolved, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gap.id,
                    self.session_id,
                    gap.description,
                    gap.severity,
                    json.dumps(gap.related_hypothesis_ids),
                    json.dumps(gap.suggested_queries or []),
                    int(gap.resolved),
                    gap.created_at.isoformat(),
                ),
            )
            self.conn.commit()
            return gap
        except sqlite3.Error as exc:
            raise RuntimeError(
                f"CRITICAL: Failed to persist knowledge gap '{gap.description[:80]}'"
            ) from exc

    def resolve_knowledge_gap(self, gap_id: str) -> bool:
        """Mark a knowledge gap as resolved."""
        cursor = self.conn.execute(
            """
            UPDATE knowledge_gaps
            SET resolved = 1, resolved_at = ?
            WHERE id = ? AND session_id = ?
            """,
            (datetime.utcnow().isoformat(), gap_id, self.session_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_all_knowledge_gaps(self) -> List[KnowledgeGap]:
        """Get all knowledge gaps."""
        rows = self.conn.execute(
            "SELECT * FROM knowledge_gaps WHERE session_id = ? ORDER BY created_at",
            (self.session_id,),
        ).fetchall()
        return [self._row_to_gap(row) for row in rows]

    def get_unresolved_gaps(self) -> List[KnowledgeGap]:
        """Get unresolved knowledge gaps."""
        rows = self.conn.execute(
            """
            SELECT * FROM knowledge_gaps
            WHERE session_id = ? AND resolved = 0
            ORDER BY severity DESC
            """,
            (self.session_id,),
        ).fetchall()
        return [self._row_to_gap(row) for row in rows]

    def get_normalized_gap_severity(self) -> float:
        """Get normalized gap severity (average of unresolved gap severities)."""
        gaps = self.get_unresolved_gaps()
        if not gaps:
            return 0.0
        return sum(g.severity for g in gaps) / len(gaps)

    # ─── Aggregate Queries ────────────────────────────────────────────────

    def get_session_summary(self) -> Dict:
        """Get a summary of the current session state."""
        return {
            "session_id": self.session_id,
            "total_claims": self.claim_store.count_claims(),
            "total_sources": self.source_registry.count_sources(),
            "total_hypotheses": len(self.hypothesis_graph.get_all_hypotheses()),
            "unresolved_gaps": len(self.get_unresolved_gaps()),
            "graph_nodes": self.hypothesis_graph.graph.number_of_nodes(),
            "graph_edges": self.hypothesis_graph.graph.number_of_edges(),
        }

    def get_source_credibility_variance(self) -> float:
        """Get source credibility variance for EpistemicRisk."""
        return self.source_registry.get_credibility_variance()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    @staticmethod
    def _row_to_gap(row: sqlite3.Row) -> KnowledgeGap:
        """Convert a database row to a KnowledgeGap."""
        return KnowledgeGap(
            id=row["id"],
            description=row["description"],
            severity=row["severity"],
            related_hypothesis_ids=json.loads(row["related_hypothesis_ids"] or "[]"),
            suggested_queries=json.loads(row["suggested_queries"] or "[]"),
            resolved=bool(row["resolved"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        )
