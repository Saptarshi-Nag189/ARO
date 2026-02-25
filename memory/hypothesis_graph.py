"""
Hypothesis Graph
================
Hypothesis CRUD with NetworkX in-memory graph for
claim → hypothesis and hypothesis → hypothesis relationships.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from schemas.hypotheses import Hypothesis, HypothesisStatus


class HypothesisGraph:
    """Manages hypotheses with an in-memory NetworkX graph."""

    def __init__(self, conn: sqlite3.Connection, session_id: str):
        self.conn = conn
        self.session_id = session_id
        self.graph = nx.DiGraph()
        self._load_graph()

    def _load_graph(self) -> None:
        """Load existing hypotheses into the graph from DB."""
        hypotheses = self.get_all_hypotheses()
        for h in hypotheses:
            self.graph.add_node(h.id, hypothesis=h)
            # Add edges for supporting claims
            for claim_id in h.supporting_claim_ids:
                self.graph.add_edge(claim_id, h.id, relation="supports")
            # Add edges for opposing claims
            for claim_id in h.opposing_claim_ids:
                self.graph.add_edge(claim_id, h.id, relation="opposes")
            # Add edges for related hypotheses
            for related_id in h.related_hypothesis_ids:
                self.graph.add_edge(h.id, related_id, relation="related")

    def add_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        """Add a hypothesis to the DB and graph."""
        if not hypothesis.id:
            hypothesis.id = f"hyp_{uuid.uuid4().hex[:12]}"

        if self.get_hypothesis(hypothesis.id):
            raise sqlite3.IntegrityError(
                f"Hypothesis ID collision within session '{self.session_id}': {hypothesis.id}"
            )

        self._insert_hypothesis(hypothesis)

        # Add to graph
        self.graph.add_node(hypothesis.id, hypothesis=hypothesis)
        for claim_id in hypothesis.supporting_claim_ids:
            self.graph.add_edge(claim_id, hypothesis.id, relation="supports")
        for claim_id in hypothesis.opposing_claim_ids:
            self.graph.add_edge(claim_id, hypothesis.id, relation="opposes")
        for related_id in hypothesis.related_hypothesis_ids:
            self.graph.add_edge(hypothesis.id, related_id, relation="related")

        return hypothesis

    def update_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        """Update an existing hypothesis."""
        hypothesis.updated_at = datetime.utcnow()

        self.conn.execute(
            """
            UPDATE hypotheses
            SET statement = ?, supporting_claim_ids = ?, opposing_claim_ids = ?,
                confidence = ?, status = ?, related_hypothesis_ids = ?,
                knowledge_gap_ids = ?, updated_at = ?
            WHERE id = ? AND session_id = ?
            """,
            (
                hypothesis.statement,
                json.dumps(hypothesis.supporting_claim_ids),
                json.dumps(hypothesis.opposing_claim_ids),
                hypothesis.confidence,
                hypothesis.status.value if isinstance(hypothesis.status, HypothesisStatus) else hypothesis.status,
                json.dumps(hypothesis.related_hypothesis_ids),
                json.dumps(hypothesis.knowledge_gap_ids),
                hypothesis.updated_at.isoformat(),
                hypothesis.id,
                self.session_id,
            ),
        )
        self.conn.commit()

        # Update graph node
        if hypothesis.id in self.graph:
            self.graph.nodes[hypothesis.id]["hypothesis"] = hypothesis

        return hypothesis

    def get_hypothesis(self, hyp_id: str) -> Optional[Hypothesis]:
        """Get a hypothesis by ID."""
        row = self.conn.execute(
            "SELECT * FROM hypotheses WHERE id = ? AND session_id = ?",
            (hyp_id, self.session_id),
        ).fetchone()
        if not row:
            return None
        return self._row_to_hypothesis(row)

    def get_all_hypotheses(self) -> List[Hypothesis]:
        """Get all hypotheses for the current session."""
        rows = self.conn.execute(
            "SELECT * FROM hypotheses WHERE session_id = ? ORDER BY created_at",
            (self.session_id,),
        ).fetchall()
        return [self._row_to_hypothesis(row) for row in rows]

    def get_supporting_claims(self, hyp_id: str) -> List[str]:
        """Get IDs of claims that support a hypothesis (from graph)."""
        return [
            u for u, v, d in self.graph.in_edges(hyp_id, data=True)
            if d.get("relation") == "supports"
        ]

    def get_opposing_claims(self, hyp_id: str) -> List[str]:
        """Get IDs of claims that oppose a hypothesis (from graph)."""
        return [
            u for u, v, d in self.graph.in_edges(hyp_id, data=True)
            if d.get("relation") == "opposes"
        ]

    def get_bridge_nodes(self) -> List[str]:
        """
        Find bridge nodes in the graph — nodes that connect otherwise
        disconnected components. Used for NoveltyScore.GraphBridgeScore.
        """
        undirected = self.graph.to_undirected()
        if undirected.number_of_nodes() < 2:
            return []
        bridges = list(nx.bridges(undirected))
        bridge_nodes: Set[str] = set()
        for u, v in bridges:
            bridge_nodes.add(u)
            bridge_nodes.add(v)
        return list(bridge_nodes)

    def compute_graph_bridge_score(self) -> float:
        """
        Compute the GraphBridgeScore: ratio of bridge nodes to total nodes.
        Higher score indicates more novel connections between knowledge clusters.
        """
        total_nodes = self.graph.number_of_nodes()
        if total_nodes == 0:
            return 0.0
        bridge_nodes = self.get_bridge_nodes()
        return len(bridge_nodes) / total_nodes

    def get_connected_components_count(self) -> int:
        """Get the number of weakly connected components."""
        if self.graph.number_of_nodes() == 0:
            return 0
        return nx.number_weakly_connected_components(self.graph)

    def _insert_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Insert a hypothesis into the database."""
        status_val = hypothesis.status.value if isinstance(hypothesis.status, HypothesisStatus) else hypothesis.status
        try:
            self.conn.execute(
                """
                INSERT INTO hypotheses (id, session_id, statement, supporting_claim_ids,
                                        opposing_claim_ids, confidence, status,
                                        related_hypothesis_ids, knowledge_gap_ids,
                                        created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.id,
                    self.session_id,
                    hypothesis.statement,
                    json.dumps(hypothesis.supporting_claim_ids),
                    json.dumps(hypothesis.opposing_claim_ids),
                    hypothesis.confidence,
                    status_val,
                    json.dumps(hypothesis.related_hypothesis_ids),
                    json.dumps(hypothesis.knowledge_gap_ids),
                    hypothesis.created_at.isoformat(),
                    hypothesis.updated_at.isoformat(),
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise

    @staticmethod
    def _row_to_hypothesis(row: sqlite3.Row) -> Hypothesis:
        """Convert a database row to a Hypothesis object."""
        return Hypothesis(
            id=row["id"],
            statement=row["statement"],
            supporting_claim_ids=json.loads(row["supporting_claim_ids"] or "[]"),
            opposing_claim_ids=json.loads(row["opposing_claim_ids"] or "[]"),
            confidence=row["confidence"],
            status=HypothesisStatus(row["status"]),
            related_hypothesis_ids=json.loads(row["related_hypothesis_ids"] or "[]"),
            knowledge_gap_ids=json.loads(row["knowledge_gap_ids"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
