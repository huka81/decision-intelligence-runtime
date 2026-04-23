"""Tests for Saga Compensation (DIR §7)."""

import tempfile
from pathlib import Path

from dir_core.models import CompensationAction
from dir_core.saga import SagaCompensation


def test_mark_dirty_and_get() -> None:
    """mark_dirty records state; get_dirty_flows returns dfids."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        saga = SagaCompensation(path)
        saga.mark_dirty("df1", "step2", {"sold": 100, "balance": 50})
        assert saga.get_dirty_flows() == ["df1"]
        state = saga.get_dirty_state("df1")
        assert state["failed_step"] == "step2"
        assert state["partial_state"]["sold"] == 100
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_execute_compensation_revert() -> None:
    """REVERT calls callback and clears dirty state."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        reverted = []

        def revert_cb(dfid: str, state: dict) -> bool:
            reverted.append((dfid, state))
            return True

        saga = SagaCompensation(path, revert_callback=revert_cb)
        saga.mark_dirty("df1", "step2", {"x": 1})
        r = saga.execute_compensation("df1", CompensationAction.REVERT)
        assert r.success is True
        assert reverted == [("df1", {"x": 1})]
        assert saga.get_dirty_flows() == []
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_execute_compensation_alert_human() -> None:
    """ALERT_HUMAN invokes callback."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        alerted = []

        def alert_cb(dfid: str, state: dict) -> None:
            alerted.append((dfid, state))

        saga = SagaCompensation(path, alert_human_callback=alert_cb)
        saga.mark_dirty("df1", "step2", {"err": "timeout"})
        r = saga.execute_compensation("df1", CompensationAction.ALERT_HUMAN)
        assert r.success is True
        assert alerted == [("df1", {"err": "timeout"})]
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_execute_compensation_noop() -> None:
    """NOOP succeeds without callback."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        saga = SagaCompensation(path)
        saga.mark_dirty("df1", "s", {})
        r = saga.execute_compensation("df1", CompensationAction.NOOP)
        assert r.success is True
        assert saga.get_dirty_flows() == ["df1"]
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite

