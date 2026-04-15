"""Tests for ContextStore (DIR §8)."""

import tempfile
from pathlib import Path

import pytest

from dir_core.context_store import ContextStore
from dir_core.storage.memory import MemoryContextStorage


def test_context_store_requires_backend() -> None:
    with pytest.raises(ValueError, match="Provide either"):
        ContextStore()


def test_session_merge_and_get() -> None:
    store = ContextStore(storage=MemoryContextStorage())
    store.update_session("df1", {"a": 1})
    store.update_session("df1", {"b": 2})
    assert store.get_session("df1") == {"a": 1, "b": 2}


def test_empty_session_returns_empty_dict() -> None:
    store = ContextStore(storage=MemoryContextStorage())
    assert store.get_session("missing") == {}


def test_state_merge_and_get() -> None:
    store = ContextStore(storage=MemoryContextStorage())
    store.update_state("agent_x", {"ver": 1})
    store.update_state("agent_x", {"flags": ["A"]})
    assert store.get_state("agent_x") == {"ver": 1, "flags": ["A"]}


def test_compile_working_context_shape() -> None:
    store = ContextStore(storage=MemoryContextStorage())
    store.update_session("df9", {"tick": 3})
    store.update_state("agent_y", {"mode": "dry_run"})
    ctx = store.compile_working_context("agent_y", "df9")
    assert ctx["meta"] == {
        "agent_id": "agent_y",
        "dfid": "df9",
        "source": "ContextStore",
    }
    assert ctx["session"] == {"tick": 3}
    assert ctx["state"] == {"mode": "dry_run"}
    assert ctx["memory"] == {}
    assert ctx["artifacts"] == {}


def test_context_store_sqlite_db_path() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        store = ContextStore(db_path=path)
        store.update_session("df-sql", {"k": "v"})
        store2 = ContextStore(db_path=path)
        assert store2.get_session("df-sql") == {"k": "v"}
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
