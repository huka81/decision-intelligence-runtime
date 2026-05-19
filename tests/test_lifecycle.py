"""Tests for DecisionFlow lifecycle transitions (DIR §4.3)."""

import tempfile
from pathlib import Path
from typing import Optional

from dir_core.intent_retry import IntentRetryGovernor
from dir_core.lifecycle import FlowStatus, transition


class _RecordingLifecycleStorage:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, Optional[str]]] = []

    def record_transition(
        self,
        dfid: str,
        from_status: str,
        to_status: str,
        *,
        root_dfid: Optional[str] = None,
    ) -> None:
        self.rows.append((dfid, from_status, to_status, root_dfid))


def test_transition_persists_via_custom_storage() -> None:
    """transition() calls storage.record_transition with string statuses."""
    store = _RecordingLifecycleStorage()
    transition(
        "df-1",
        FlowStatus.CREATED,
        FlowStatus.ACTIVE,
        storage=store,
    )
    assert store.rows == [("df-1", "CREATED", "ACTIVE", None)]


def test_transition_no_storage_when_omitted() -> None:
    """Without db_path or storage, only side effects are in-process (e.g. governor)."""
    transition("df-x", FlowStatus.ACTIVE, FlowStatus.VALIDATING)


def test_transition_resets_retry_governor_on_closed() -> None:
    """Terminal CLOSED clears IntentRetryGovernor for the dfid."""
    gov = IntentRetryGovernor(max_retries=2, db_path=None)
    assert gov.record_rejection("df1") == 1
    assert gov.record_rejection("df1") == 2
    assert gov.should_abort("df1") is True

    transition(
        "df1",
        FlowStatus.EXECUTING,
        FlowStatus.CLOSED,
        retry_governor=gov,
    )
    assert gov.should_abort("df1") is False
    assert gov.record_rejection("df1") == 1


def test_transition_resets_retry_governor_on_aborted() -> None:
    """Terminal ABORTED also resets the governor."""
    gov = IntentRetryGovernor(max_retries=1, db_path=None)
    assert gov.record_rejection("df2") == 1
    assert gov.should_abort("df2") is True
    transition("df2", FlowStatus.ACTIVE, FlowStatus.ABORTED, retry_governor=gov)
    assert gov.should_abort("df2") is False


def test_transition_non_terminal_does_not_reset_governor() -> None:
    """Non-terminal transitions do not call governor.reset."""
    gov = IntentRetryGovernor(max_retries=5, db_path=None)
    assert gov.record_rejection("df3") == 1
    transition("df3", FlowStatus.ACTIVE, FlowStatus.VALIDATING, retry_governor=gov)
    assert gov.record_rejection("df3") == 2


def test_transition_sqlite_db_path() -> None:
    """db_path wires SqliteLifecycleStorage (integration)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        transition("df-s", FlowStatus.CREATED, FlowStatus.ACTIVE, db_path=path)
        import sqlite3

        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(
                "SELECT dfid, root_dfid, from_status, to_status FROM flow_transitions WHERE dfid = ?",
                ("df-s",),
            )
            row = cur.fetchone()
            assert row == ("df-s", "df-s", "CREATED", "ACTIVE")
        finally:
            conn.close()
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def test_storage_kwarg_overrides_db_path() -> None:
    """When both storage and db_path are passed, only custom storage is used."""
    store = _RecordingLifecycleStorage()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        unused_sqlite = f.name
    try:
        transition(
            "df-p",
            FlowStatus.ACTIVE,
            FlowStatus.CLOSED,
            db_path=unused_sqlite,
            storage=store,
        )
        assert store.rows == [("df-p", "ACTIVE", "CLOSED", None)]
    finally:
        try:
            Path(unused_sqlite).unlink(missing_ok=True)
        except OSError:
            pass
