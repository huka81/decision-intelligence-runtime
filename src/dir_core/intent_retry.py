"""
Intent Retry Governor (DIR §6.2).

Limits correction attempts per DFID. After max_retries rejections,
flow must be aborted with REASONING_EXHAUSTION to prevent feedback poisoning.
"""

import logging
from typing import Dict, Optional

from .storage.base import IntentRetryStorage
from .storage.memory import MemoryIntentRetryStorage
from .storage.sqlite import SqliteIntentRetryStorage

logger = logging.getLogger(__name__)

REASONING_EXHAUSTION = "REASONING_EXHAUSTION"


class IntentRetryGovernor:
    """Tracks rejection count per DFID; enforces max retries before abort.

    Storage backend is pluggable. The default is in-memory when neither
    ``db_path`` nor ``storage`` is provided.

    Args:
        max_retries: Maximum number of allowed rejections before abort.
        db_path: Path to SQLite database for persistent counting.
        storage: Custom :class:`~dir_core.storage.IntentRetryStorage` backend.
            When provided, ``db_path`` is ignored.
    """

    def __init__(
        self,
        max_retries: int = 3,
        db_path: Optional[str] = None,
        *,
        storage: Optional[IntentRetryStorage] = None,
    ):
        self.max_retries = max_retries

        if storage is not None:
            self._storage: IntentRetryStorage = storage
        elif db_path is not None:
            self.db_path = db_path  # kept for backward compatibility
            self._storage = SqliteIntentRetryStorage(db_path)
        else:
            self._storage = MemoryIntentRetryStorage()

    def record_rejection(self, dfid: str) -> int:
        """Increment rejection count for dfid; return new count."""
        count = self._storage.get_count(dfid) + 1
        self._storage.set_count(dfid, count)
        logger.debug("Intent retry: dfid=%s count=%d", dfid, count)
        return count

    def should_abort(self, dfid: str) -> bool:
        """True if count >= max_retries (flow must be aborted)."""
        return self._storage.get_count(dfid) >= self.max_retries

    def reset(self, dfid: str) -> None:
        """Clear rejection count when flow ends (CLOSED/ABORTED)."""
        self._storage.delete(dfid)
