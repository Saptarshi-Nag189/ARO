"""
Checkpointer Factory
====================
Durable execution backend for the graphs.

- Default: SqliteSaver writing aro_checkpoints.db next to the app —
  zero-config local durability (resume a crashed run with --resume).
- Production: set ARO_CHECKPOINT_URI=postgresql://... (RDS in the AWS
  deployment) and every run survives container restarts and can be
  resumed from any node boundary.
"""

import os
import sqlite3
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

def _allowed_state_classes() -> list:
    """Every Pydantic model / enum defined under schemas/ is trusted state.

    The serializer requires exact (module, class) entries; enumerating the
    schema modules keeps the allowlist automatically in sync with new
    schema classes.
    """
    import enum
    import inspect

    import schemas.agent_io
    import schemas.claims
    import schemas.hypotheses
    import schemas.knowledge_gaps
    import schemas.reports
    import schemas.search_result
    import schemas.sources
    from pydantic import BaseModel

    modules = [
        schemas.agent_io, schemas.claims, schemas.hypotheses,
        schemas.knowledge_gaps, schemas.reports, schemas.search_result,
        schemas.sources,
    ]
    allowed = []
    for mod in modules:
        for obj in vars(mod).values():
            if (
                inspect.isclass(obj)
                and obj.__module__ == mod.__name__
                and (issubclass(obj, BaseModel) or issubclass(obj, enum.Enum))
            ):
                allowed.append(obj)
    return allowed


def _serde() -> JsonPlusSerializer:
    """Serializer with our schema classes allowlisted.

    Tolerates serde API differences across langgraph-checkpoint versions:
    if this version doesn't accept an explicit allowlist, fall back to the
    default (permissive) serializer rather than failing to construct.
    """
    import inspect

    params = inspect.signature(JsonPlusSerializer.__init__).parameters
    if "allowed_msgpack_modules" in params:
        return JsonPlusSerializer(allowed_msgpack_modules=_allowed_state_classes())
    return JsonPlusSerializer()


def get_checkpointer(base_dir: Optional[str] = None) -> BaseCheckpointSaver:
    uri = os.getenv("ARO_CHECKPOINT_URI", "").strip()

    if uri.startswith("postgres"):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg import Connection
        except ImportError as exc:
            raise ImportError(
                "ARO_CHECKPOINT_URI is set to Postgres but the driver is "
                "missing. Install with: pip install langgraph-checkpoint-postgres"
            ) from exc
        conn = Connection.connect(uri, autocommit=True, prepare_threshold=0)
        saver = PostgresSaver(conn, serde=_serde())
        saver.setup()
        return saver

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = os.getenv("ARO_CHECKPOINT_SQLITE", "aro_checkpoints.db")
    if base_dir and not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    # LangGraph nodes may execute on worker threads; the saver serializes
    # access internally, so cross-thread use of this connection is safe.
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn, serde=_serde())
