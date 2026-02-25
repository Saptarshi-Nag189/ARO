"""
Source Registry
===============
CRUD operations for research sources with credibility scoring.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

from schemas.sources import Source


class SourceRegistry:
    """Manages source persistence and credibility tracking."""

    def __init__(self, conn: sqlite3.Connection, session_id: str):
        self.conn = conn
        self.session_id = session_id

    def add_source(self, source: Source) -> Source:
        """Register a new source."""
        if not source.id:
            source.id = f"src_{uuid.uuid4().hex[:12]}"

        self.conn.execute(
            """
            INSERT INTO sources (id, session_id, url, title, authors,
                                 publication_date, source_type, credibility_score,
                                 content_summary, retrieved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                self.session_id,
                source.url,
                source.title,
                json.dumps(source.authors or []),
                source.publication_date,
                source.source_type,
                source.credibility_score,
                source.content_summary,
                source.retrieved_at.isoformat(),
            ),
        )
        self.conn.commit()
        return source

    def get_source(self, source_id: str) -> Optional[Source]:
        """Get a source by ID."""
        row = self.conn.execute(
            "SELECT * FROM sources WHERE id = ? AND session_id = ?",
            (source_id, self.session_id),
        ).fetchone()
        if not row:
            return None
        return self._row_to_source(row)

    def get_all_sources(self) -> List[Source]:
        """Get all sources for the current session."""
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE session_id = ? ORDER BY retrieved_at",
            (self.session_id,),
        ).fetchall()
        return [self._row_to_source(row) for row in rows]

    def update_credibility(self, source_id: str, new_score: float) -> bool:
        """Update the credibility score of a source."""
        cursor = self.conn.execute(
            "UPDATE sources SET credibility_score = ? WHERE id = ? AND session_id = ?",
            (round(max(0.0, min(1.0, new_score)), 6), source_id, self.session_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_credibility_variance(self) -> float:
        """Compute variance of source credibility scores. Used in EpistemicRisk."""
        sources = self.get_all_sources()
        if len(sources) < 2:
            return 0.0
        scores = [s.credibility_score for s in sources]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return variance

    def count_sources(self) -> int:
        """Count total sources for this session."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM sources WHERE session_id = ?",
            (self.session_id,),
        ).fetchone()
        return row["cnt"]

    @staticmethod
    def _row_to_source(row: sqlite3.Row) -> Source:
        """Convert a database row to a Source object."""
        return Source(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            authors=json.loads(row["authors"] or "[]"),
            publication_date=row["publication_date"],
            source_type=row["source_type"],
            credibility_score=row["credibility_score"],
            content_summary=row["content_summary"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
        )
