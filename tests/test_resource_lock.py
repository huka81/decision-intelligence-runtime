"""Tests for Resource Lock Manager (DIR §6.2)."""

import tempfile
from pathlib import Path

from dir_core.resource_lock import LockResult, ResourceLockManager


def test_acquire_and_release() -> None:
    """Acquire succeeds when resources available; release frees them."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        avail = {"capital": 1000.0}
        def prov(r: str) -> float:
            return avail.get(r, 0.0)

        rlm = ResourceLockManager(path, prov)
        res = rlm.acquire("df1", {"capital": 500.0})
        assert res == LockResult.ACQUIRED

        # Second flow wants 600 - only 500 free
        res2 = rlm.acquire("df2", {"capital": 600.0})
        assert res2 == LockResult.INSUFFICIENT_LIQUIDITY

        rlm.release("df1")
        res3 = rlm.acquire("df2", {"capital": 600.0})
        assert res3 == LockResult.ACQUIRED
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_lock_normalization_alphabetical() -> None:
    """Resources acquired in alphabetical order (Lock Normalization)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        def prov(r: str) -> float:
            return 100.0

        rlm = ResourceLockManager(path, prov)
        res = rlm.acquire("df1", {"zebra": 10.0, "alpha": 10.0})
        assert res == LockResult.ACQUIRED
        rlm.release("df1")
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite

