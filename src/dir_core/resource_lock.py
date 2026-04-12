"""
Resource Locking / Semantic Locking (DIR §6.2, §2.3).

Reservation locks for shared resources (capital, API throughput).
Linear Lock Acquisition (alphabetical order) to prevent deadlocks.
"""

import sqlite3
import logging
import time
from enum import Enum
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class LockResult(str, Enum):
    """Result of acquire attempt."""

    ACQUIRED = "ACQUIRED"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    RESOURCE_CONTENTION_TIMEOUT = "RESOURCE_CONTENTION_TIMEOUT"


class ResourceLockManager:
    """Manages reservation locks for shared resources (DIR §6.2)."""

    def __init__(
        self,
        db_path: str,
        availability_provider: Callable[[str], float],
    ):
        self.db_path = db_path
        self.availability_provider = availability_provider
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resource_locks (
                    dfid TEXT,
                    resource_id TEXT,
                    amount REAL,
                    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (dfid, resource_id)
                )
            """)
            conn.commit()

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
        # Lock Normalization (DIR Topologies §6.4)
        sorted_ids = sorted(resources.keys())
        deadline = time.monotonic() + timeout_sec

        while time.monotonic() < deadline:
            try:
                conn = sqlite3.connect(self.db_path, timeout=0.1)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for rid in sorted_ids:
                        amount = resources[rid]
                        available = self.availability_provider(rid)
                        locked = self._locked_amount_conn(conn, rid, dfid)
                        free = available - locked
                        if free < amount:
                            conn.rollback()
                            conn.close()
                            return LockResult.INSUFFICIENT_LIQUIDITY
                    for rid in sorted_ids:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO resource_locks
                            (dfid, resource_id, amount) VALUES (?, ?, ?)
                            """,
                            (dfid, rid, resources[rid]),
                        )
                    conn.commit()
                    conn.close()
                    return LockResult.ACQUIRED
                except Exception:
                    conn.rollback()
                    conn.close()
                    raise
            except sqlite3.OperationalError:
                time.sleep(0.05)
                continue

        return LockResult.RESOURCE_CONTENTION_TIMEOUT

    def _locked_amount_conn(
        self, conn: sqlite3.Connection, resource_id: str, exclude_dfid: str
    ) -> float:
        """Sum locked amount for resource (excluding exclude_dfid)."""
        cursor = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM resource_locks
            WHERE resource_id = ? AND dfid != ?
            """,
            (resource_id, exclude_dfid),
        )
        row = cursor.fetchone()
        return float(row[0]) if row else 0.0

    def release(self, dfid: str) -> None:
        """Release all locks held by dfid."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM resource_locks WHERE dfid = ?", (dfid,))
            conn.commit()
