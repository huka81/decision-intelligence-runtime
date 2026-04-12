"""
Resource Locking / Semantic Locking (DIR §6.2, §2.3).

Reservation locks for shared resources (capital, API throughput).
Linear Lock Acquisition (alphabetical order) to prevent deadlocks.
"""

import logging
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

    Storage backend is pluggable. Pass ``storage=`` for a custom backend, or
    ``db_path=`` to use the built-in SQLite backend (default behaviour).

    Args:
        db_path: Path to SQLite database. Used when ``storage`` is not provided.
        availability_provider: Callable(resource_id) -> total available amount.
        storage: Custom :class:`~dir_core.storage.ResourceLockStorage` backend.
            When provided, ``db_path`` is ignored.

    Raises:
        ValueError: When neither ``db_path`` nor ``storage`` is supplied.
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
        """
        Acquire locks for resources. Resources normalized (alphabetical).
        Returns ACQUIRED, INSUFFICIENT_LIQUIDITY, or RESOURCE_CONTENTION_TIMEOUT.
        """
        result = self._storage.try_acquire_atomic(
            dfid=dfid,
            resources=resources,
            availability_provider=self.availability_provider,
            timeout_sec=timeout_sec,
        )
        return LockResult(result)

    def release(self, dfid: str) -> None:
        """Release all locks held by dfid."""
        self._storage.release(dfid)
