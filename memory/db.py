"""
Database Initialization
=======================
SQLite connection factory, schema creation, and in-place legacy migration.
"""

import sqlite3
from typing import Dict, List


_TABLE_SQL: Dict[str, str] = {
    "sessions": """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    research_objective TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'autonomous',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'active'
);
""",
    "sources": """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    url TEXT,
    title TEXT NOT NULL,
    authors TEXT,
    publication_date TEXT,
    source_type TEXT NOT NULL DEFAULT 'web',
    credibility_score REAL NOT NULL DEFAULT 0.5,
    content_summary TEXT,
    retrieved_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
""",
    "claims": """
CREATE TABLE IF NOT EXISTS claims (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    relation TEXT NOT NULL,
    object TEXT NOT NULL,
    qualifiers TEXT,
    source_id TEXT NOT NULL,
    confidence_estimate REAL NOT NULL,
    credibility_weight REAL NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    merged_from TEXT,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (session_id, source_id) REFERENCES sources(session_id, id)
);
""",
    "hypotheses": """
CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    supporting_claim_ids TEXT,
    opposing_claim_ids TEXT,
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'proposed',
    related_hypothesis_ids TEXT,
    knowledge_gap_ids TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
""",
    "knowledge_gaps": """
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    description TEXT NOT NULL,
    severity REAL NOT NULL DEFAULT 0.5,
    related_hypothesis_ids TEXT,
    suggested_queries TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT,
    PRIMARY KEY (session_id, id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
""",
}

_CREATE_TABLES_SQL = "\n".join(
    _TABLE_SQL[name] for name in (
        "sessions",
        "sources",
        "claims",
        "hypotheses",
        "knowledge_gaps",
    )
)

_COMPOSITE_PK_TABLES = ("sources", "claims", "hypotheses", "knowledge_gaps")
_MIGRATION_ORDER = ("sources", "claims", "hypotheses", "knowledge_gaps")
_TABLE_COLUMNS: Dict[str, List[str]] = {
    "sources": [
        "id",
        "session_id",
        "url",
        "title",
        "authors",
        "publication_date",
        "source_type",
        "credibility_score",
        "content_summary",
        "retrieved_at",
    ],
    "claims": [
        "id",
        "session_id",
        "subject",
        "relation",
        "object",
        "qualifiers",
        "source_id",
        "confidence_estimate",
        "credibility_weight",
        "timestamp",
        "merged_from",
        "evidence_count",
    ],
    "hypotheses": [
        "id",
        "session_id",
        "statement",
        "supporting_claim_ids",
        "opposing_claim_ids",
        "confidence",
        "status",
        "related_hypothesis_ids",
        "knowledge_gap_ids",
        "created_at",
        "updated_at",
    ],
    "knowledge_gaps": [
        "id",
        "session_id",
        "description",
        "severity",
        "related_hypothesis_ids",
        "suggested_queries",
        "resolved",
        "created_at",
        "resolved_at",
    ],
}


def get_connection(db_path: str = "aro_memory.db") -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_database(db_path: str = "aro_memory.db") -> sqlite3.Connection:
    """
    Initialize database with all tables and run in-place migration if needed.

    Raises:
        RuntimeError: If migration or post-migration integrity checks fail.
    """
    conn = get_connection(db_path)
    conn.executescript(_CREATE_TABLES_SQL)
    _migrate_legacy_schema_if_needed(conn)
    _assert_schema_integrity(conn)
    conn.commit()
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_pk_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    ordered = sorted(
        (row for row in rows if row["pk"] > 0),
        key=lambda row: row["pk"],
    )
    return [row["name"] for row in ordered]


def _needs_composite_pk_migration(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    if not _table_exists(conn, table_name):
        return False
    return _get_pk_columns(conn, table_name) != ["session_id", "id"]


def _migrate_legacy_schema_if_needed(conn: sqlite3.Connection) -> None:
    tables_to_migrate = [
        table for table in _COMPOSITE_PK_TABLES
        if _needs_composite_pk_migration(conn, table)
    ]
    if not tables_to_migrate:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN")
        for table_name in _MIGRATION_ORDER:
            if table_name not in tables_to_migrate:
                continue
            _migrate_table_to_composite_pk(conn, table_name)
        conn.commit()
    except Exception as exc:  # pragma: no cover - fatal path
        conn.rollback()
        raise RuntimeError(
            f"CRITICAL: In-place DB migration failed: {exc}"
        ) from exc
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _migrate_table_to_composite_pk(
    conn: sqlite3.Connection,
    table_name: str,
) -> None:
    backup_table = f"{table_name}__legacy_backup"
    if _table_exists(conn, backup_table):
        raise RuntimeError(
            f"CRITICAL: Migration blocked; backup table '{backup_table}' already exists."
        )

    conn.execute(f"ALTER TABLE {table_name} RENAME TO {backup_table}")
    conn.execute(_TABLE_SQL[table_name])

    expected_cols = _TABLE_COLUMNS[table_name]
    legacy_cols = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({backup_table})").fetchall()
    }
    missing = [col for col in expected_cols if col not in legacy_cols]
    if missing:
        raise RuntimeError(
            f"CRITICAL: Legacy table '{backup_table}' missing required columns: {missing}"
        )

    col_csv = ", ".join(expected_cols)
    conn.execute(
        f"INSERT INTO {table_name} ({col_csv}) "
        f"SELECT {col_csv} FROM {backup_table}"
    )
    conn.execute(f"DROP TABLE {backup_table}")


def _assert_schema_integrity(conn: sqlite3.Connection) -> None:
    for table_name in _COMPOSITE_PK_TABLES:
        pk_cols = _get_pk_columns(conn, table_name)
        if pk_cols != ["session_id", "id"]:
            raise RuntimeError(
                f"CRITICAL: Schema validation failed for '{table_name}'. "
                f"Expected composite PK ['session_id', 'id'], got {pk_cols}."
            )

    fk_rows = conn.execute("PRAGMA foreign_key_list(claims)").fetchall()
    fk_groups: Dict[int, Dict[str, object]] = {}
    for row in fk_rows:
        group = fk_groups.setdefault(
            row["id"],
            {"table": row["table"], "pairs": []},
        )
        group["pairs"].append((row["from"], row["to"]))

    has_composite_claim_source_fk = any(
        group["table"] == "sources"
        and sorted(group["pairs"]) == [("session_id", "session_id"), ("source_id", "id")]
        for group in fk_groups.values()
    )
    if not has_composite_claim_source_fk:
        raise RuntimeError(
            "CRITICAL: claims table missing composite foreign key "
            "(session_id, source_id) -> sources(session_id, id)."
        )

    fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_issues:
        issue_summary = [
            {
                "table": row["table"],
                "rowid": row["rowid"],
                "parent": row["parent"],
                "fkid": row["fkid"],
            }
            for row in fk_issues
        ]
        raise RuntimeError(
            f"CRITICAL: foreign_key_check failed after migration: {issue_summary}"
        )
