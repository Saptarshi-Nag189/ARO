"""Shared test fixtures."""

import os
import sys

import pytest

# Make the repo root importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.memory_service import MemoryService  # noqa: E402


@pytest.fixture
def memory(tmp_path):
    """A MemoryService on a throwaway DB, vector store disabled (no chromadb)."""
    svc = MemoryService(
        db_path=str(tmp_path / "test.db"),
        session_id="session_testtesttest",
        enable_cross_session_memory=False,
    )
    svc.create_session("test objective", "autonomous")
    yield svc
    svc.close()
