"""
Resource Locking / Semantic Locking (DIR §6.2, §2.3).

Reservation locks for shared resources (capital, API throughput).
Linear Lock Acquisition (alphabetical order) to prevent deadlocks.
"""

import logging
import time
from enum import Enum
from typing import Callable, Dict, Optional

from .storage.base import ResourceLockStorage
from .storage.sqlite import SqliteResourceLockStorage

logger = logging.getLogger(__name__)


class LockResult(str, Enum):
    """Result of acquire attempt."""

    ACQUIRED = "ACQUIRED"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    RESOURCE_CONTENTION_TIMEOUT = "RESOURCE_CONTENTION_TIMEOUT"


class ResourceLockManager:
    """Manages reservation locks for shared resources (DIR §6.2).

    Responsibility split:

    - **Manager**: checks domain availability (via ``availability_provider``),
      enforces alphabetical lock ordering to prevent deadlocks, retries on
      contention.
    - **Storage backend**: provides atomic batch-write of acquired locks and
      returns the currently locked amount per resource.

    Storage backend is pluggable. Pass ``storage=`` for a custom backend, or
    ``db_path=`` to use the built-in SQLite backend (default behaviour).

    Args:
        db_path: Path to SQLite database. Used when ``storage`` is not provided.
        availability_provider: ``Callable(resource_id) -> float`` returning the
            total capacity for a given resource.
        storage: Custom :class:`~dir_core.storage.ResourceLockStorage` backend.
            When provided, ``db_path`` is ignored.

    Raises:
        ValueError: When ``availability_provider`` is missing, or when neither
            ``db_path`` nor ``storage`` is supplied.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        availability_provider: Optional[Callable[[str], float]] = None,
        *,
        storage: Optional[ResourceLockStorage] = None,
    ):
        if availability_provider is None:
            raise ValueError("availability_provider is required.")

        self.availability_provider = availability_provider

        if storage is not None:
            self._storage: ResourceLockStorage = storage
        elif db_path is not None:
            self.db_path = db_path  # kept for backward compatibility
            self._storage = SqliteResourceLockStorage(db_path)
        else:
            raise ValueError(
                "Provide either 'db_path' (SQLite) or 'storage' (custom backend)."
            )

    def acquire(
        self,
        dfid: str,
        resources: Dict[str, float],
        timeout_sec: float = 5.0,
    ) -> LockResult:
        """Acquire locks for all resources in sorted order (DIR Topologies §6.4).

        Flow:
        1. Check domain availability for each resource via
           ``availability_provider``.  Return ``INSUFFICIENT_LIQUIDITY``
           immediately if any resource is over-allocated.
        2. Ask the storage backend to write the locks atomically.  The backend
           may retry internally (SQLite uses ``BEGIN IMMEDIATE``); if it cannot
           obtain exclusive write access within *timeout_sec*, return
           ``RESOURCE_CONTENTION_TIMEOUT``.
        """
        sorted_ids = sorted(resources.keys())
        deadline = time.monotonic() + timeout_sec

        while time.monotonic() < deadline:
            # Step 1 — availability check (domain logic, outside transaction)
            for rid in sorted_ids:
                available = self.availability_provider(rid)
                locked = self._storage.get_locked_amount(rid, exclude_dfid=dfid)
                if available - locked < resources[rid]:
                    return LockResult.INSUFFICIENT_LIQUIDITY

            # Step 2 — atomic write (backend handles its own concurrency)
            remaining = max(0.0, deadline - time.monotonic())
            acquired = self._storage.acquire_batch(dfid, resources, remaining)
            if acquired:
                return LockResult.ACQUIRED

            # Backend timed out getting exclusive write access — retry
            time.sleep(0.05)

        return LockResult.RESOURCE_CONTENTION_TIMEOUT

    def release(self, dfid: str) -> None:
        """Release all locks held by dfid."""
        self._storage.release(dfid)
