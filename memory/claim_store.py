"""
Claim Store
===========
CRUD operations for claims with deduplication logic.
Uses difflib.SequenceMatcher for similarity threshold (0.85).
"""

import json
import sqlite3
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Optional

from schemas.claims import Claim


def _similarity(a: str, b: str) -> float:
    """Compute string similarity using SequenceMatcher."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class ClaimStore:
    """Manages claim persistence and deduplication."""

    SIMILARITY_THRESHOLD = 0.85

    def __init__(self, conn: sqlite3.Connection, session_id: str):
        self.conn = conn
        self.session_id = session_id

    def add_claim(self, claim: Claim) -> Claim:
        """
        Add a claim, applying deduplication rules:
        If subject similarity > 0.85 AND relation identical AND object similarity > 0.85:
            Merge claims, aggregate evidence, recalculate confidence.
        """
        # Check for duplicates
        existing = self.get_all_claims()
        for ex in existing:
            if (
                _similarity(claim.subject, ex.subject) > self.SIMILARITY_THRESHOLD
                and claim.relation.lower().strip() == ex.relation.lower().strip()
                and _similarity(claim.object, ex.object) > self.SIMILARITY_THRESHOLD
            ):
                # Merge: aggregate evidence and recalculate confidence
                return self._merge_claims(ex, claim)

        # No duplicate — insert new
        claim.id = f"claim_{uuid.uuid4().hex[:12]}"

        self._insert_claim(claim)
        return claim

    def _merge_claims(self, existing: Claim, new: Claim) -> Claim:
        """Merge a new claim into an existing one."""
        merged_from = list(existing.merged_from or [])
        if new.id:
            merged_from.append(new.id)
        else:
            merged_from.append(f"claim_{uuid.uuid4().hex[:12]}")

        new_evidence_count = existing.evidence_count + 1

        # Recalculate confidence: weighted average by evidence count
        new_confidence = (
            (existing.confidence_estimate * existing.evidence_count)
            + new.confidence_estimate
        ) / new_evidence_count

        # Recalculate credibility: max of both
        new_credibility = max(existing.credibility_weight, new.credibility_weight)

        self.conn.execute(
            """
            UPDATE claims
            SET confidence_estimate = ?,
                credibility_weight = ?,
                evidence_count = ?,
                merged_from = ?,
                timestamp = ?
            WHERE id = ? AND session_id = ?
            """,
            (
                round(new_confidence, 6),
                round(new_credibility, 6),
                new_evidence_count,
                json.dumps(merged_from),
                datetime.utcnow().isoformat(),
                existing.id,
                self.session_id,
            ),
        )
        self.conn.commit()

        # Return updated claim
        existing.confidence_estimate = round(new_confidence, 6)
        existing.credibility_weight = round(new_credibility, 6)
        existing.evidence_count = new_evidence_count
        existing.merged_from = merged_from
        return existing

    def _insert_claim(self, claim: Claim) -> None:
        """Insert a claim into the database."""
        self.conn.execute(
            """
            INSERT INTO claims (id, session_id, subject, relation, object,
                                qualifiers, source_id, confidence_estimate,
                                credibility_weight, timestamp, merged_from,
                                evidence_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim.id,
                self.session_id,
                claim.subject,
                claim.relation,
                claim.object,
                json.dumps(claim.qualifiers or []),
                claim.source_id,
                claim.confidence_estimate,
                claim.credibility_weight,
                claim.timestamp.isoformat(),
                json.dumps(claim.merged_from or []),
                claim.evidence_count,
            ),
        )
        self.conn.commit()

    def get_claim(self, claim_id: str) -> Optional[Claim]:
        """Get a claim by ID."""
        row = self.conn.execute(
            "SELECT * FROM claims WHERE id = ? AND session_id = ?",
            (claim_id, self.session_id),
        ).fetchone()
        if not row:
            return None
        return self._row_to_claim(row)

    def get_all_claims(self) -> List[Claim]:
        """Get all claims for the current session."""
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE session_id = ? ORDER BY timestamp",
            (self.session_id,),
        ).fetchall()
        return [self._row_to_claim(row) for row in rows]

    def get_claims_by_source(self, source_id: str) -> List[Claim]:
        """Get all claims from a specific source."""
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE session_id = ? AND source_id = ?",
            (self.session_id, source_id),
        ).fetchall()
        return [self._row_to_claim(row) for row in rows]

    def delete_claim(self, claim_id: str) -> bool:
        """Delete a claim by ID."""
        cursor = self.conn.execute(
            "DELETE FROM claims WHERE id = ? AND session_id = ?",
            (claim_id, self.session_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def count_claims(self) -> int:
        """Count total claims for this session."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM claims WHERE session_id = ?",
            (self.session_id,),
        ).fetchone()
        return row["cnt"]

    @staticmethod
    def _row_to_claim(row: sqlite3.Row) -> Claim:
        """Convert a database row to a Claim object."""
        return Claim(
            id=row["id"],
            subject=row["subject"],
            relation=row["relation"],
            object=row["object"],
            qualifiers=json.loads(row["qualifiers"] or "[]"),
            source_id=row["source_id"],
            confidence_estimate=row["confidence_estimate"],
            credibility_weight=row["credibility_weight"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            merged_from=json.loads(row["merged_from"] or "[]"),
            evidence_count=row["evidence_count"],
        )
