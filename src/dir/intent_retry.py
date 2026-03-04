"""
Intent Retry Governor (DIR §6.2).

Limits correction attempts per DFID. After max_retries rejections,
flow must be aborted with REASONING_EXHAUSTION to prevent feedback poisoning.
"""

import sqlite3
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

REASONING_EXHAUSTION = "REASONING_EXHAUSTION"


class IntentRetryGovernor:
    """Tracks rejection count per DFID; enforces max retries before abort."""

    def __init__(self, max_retries: int = 3, db_path: Optional[str] = None):
        self.max_retries = max_retries
        self.db_path = db_path
        self._memory: Dict[str, int] = {}
        if db_path:
            self._init_db()

    def _init_db(self) -> None:
        if not self.db_path:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intent_retry (
                    dfid TEXT PRIMARY KEY,
                    rejection_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _get_count(self, dfid: str) -> int:
        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT rejection_count FROM intent_retry WHERE dfid = ?",
                    (dfid,),
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        return self._memory.get(dfid, 0)

    def _set_count(self, dfid: str, count: int) -> None:
        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO intent_retry (dfid, rejection_count, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """,
                    (dfid, count),
                )
                conn.commit()
        else:
            self._memory[dfid] = count

    def record_rejection(self, dfid: str) -> int:
        """Increment rejection count for dfid; return new count."""
        count = self._get_count(dfid) + 1
        self._set_count(dfid, count)
        logger.debug("Intent retry: dfid=%s count=%d", dfid, count)
        return count

    def should_abort(self, dfid: str) -> bool:
        """True if count >= max_retries (flow must be aborted)."""
        return self._get_count(dfid) >= self.max_retries

    def reset(self, dfid: str) -> None:
        """Clear rejection count when flow ends (CLOSED/ABORTED)."""
        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM intent_retry WHERE dfid = ?", (dfid,))
                conn.commit()
        else:
            self._memory.pop(dfid, None)
