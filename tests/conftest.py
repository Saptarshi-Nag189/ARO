"""
Test fixtures
=============
Everything runs offline on the deterministic fake model — no API keys,
no network. Each test gets an isolated SQLite memory DB and checkpoint
store in a temp directory.
"""

import os
import sys

# Offline mode must be set before graph modules are imported.
os.environ["ARO_FAKE_MODEL"] = "1"
os.environ.pop("ARO_CHECKPOINT_URI", None)
os.environ.pop("ARO_MODEL_PROVIDER", None)

# Make the repo root importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from config import AROConfig
from graph.checkpoint import _serde
from graph.services import GraphServices
from memory.memory_service import MemoryService
from runtime.logger import SessionLogger


class EventCollector:
    """Captures every event the graph emits, in order."""

    def __init__(self):
        self.events = []

    def __call__(self, event_type, data):
        self.events.append({"type": event_type, **(data or {})})

    def types(self):
        return [e["type"] for e in self.events]

    def agents_started(self):
        return [e["agent"] for e in self.events if e["type"] == "agent_start"]


@pytest.fixture()
def config():
    cfg = AROConfig()
    cfg.min_iterations = 1
    cfg.max_iterations = 5
    return cfg


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


@pytest.fixture()
def services(tmp_path, config):
    memory = MemoryService(
        db_path=str(tmp_path / "memory.db"),
        session_id="session_test00000000",
        enable_cross_session_memory=False,
    )
    memory.create_session("Test objective", "autonomous")
    session_logger = SessionLogger(
        log_dir=str(tmp_path / "logs"),
        session_id="session_test00000000",
        mode="production",
    )
    collector = EventCollector()
    svc = GraphServices(
        config=config,
        memory=memory,
        session_logger=session_logger,
        emit=collector,
    )
    svc.events = collector  # test-only handle
    yield svc
    memory.close()
    session_logger.close()


@pytest.fixture()
def checkpointer(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "checkpoints.db"), check_same_thread=False)
    yield SqliteSaver(conn, serde=_serde())
    conn.close()


def initial_state(objective="Test objective", mode="autonomous", hitl=False):
    return {
        "objective": objective,
        "mode": mode,
        "hitl": hitl,
        "iteration": 1,
        "tokens_used": 0,
        "last_token_snapshot": 0,
    }


@pytest.fixture()
def invoke_config():
    return {
        "configurable": {"thread_id": "session_test00000000"},
        "recursion_limit": 600,
    }
