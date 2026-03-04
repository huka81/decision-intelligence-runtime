"""
Saga Compensation (DIR §7, Topologies §6.4).

Parent-Child flows: mark_dirty on partial failure, deterministic compensation.
"""

import json
import sqlite3
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .models import CompensationAction

logger = logging.getLogger(__name__)


@dataclass
class CompensationResult:
    """Result of execute_compensation."""

    success: bool
    message: str = ""


class SagaCompensation:
    """Manages dirty state and deterministic compensation (DIR §7)."""

    def __init__(
        self,
        db_path: str,
        revert_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        close_all_callback: Optional[Callable[[str], bool]] = None,
        alert_human_callback: Optional[
            Callable[[str, Dict[str, Any]], None]
        ] = None,
    ):
        self.db_path = db_path
        self.revert_callback = revert_callback
        self.close_all_callback = close_all_callback
        self.alert_human_callback = alert_human_callback
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saga_dirty_state (
                    dfid TEXT PRIMARY KEY,
                    failed_step TEXT,
                    partial_state_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def mark_dirty(
        self,
        dfid: str,
        failed_step: str,
        partial_state: Dict[str, Any],
    ) -> None:
        """Record flow as PARTIAL_SUCCESS_DIRTY after step failure."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO saga_dirty_state
                (dfid, failed_step, partial_state_json)
                VALUES (?, ?, ?)
                """,
                (dfid, failed_step, json.dumps(partial_state, default=str)),
            )
            conn.commit()
        logger.warning("Saga dirty: dfid=%s failed_step=%s", dfid, failed_step)

    def get_dirty_flows(self) -> List[str]:
        """Return list of dfids in dirty state."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT dfid FROM saga_dirty_state"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_dirty_state(self, dfid: str) -> Optional[Dict[str, Any]]:
        """Return partial state for dirty flow."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT failed_step, partial_state_json "
                "FROM saga_dirty_state WHERE dfid = ?",
                (dfid,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "failed_step": row[0],
                "partial_state": json.loads(row[1] or "{}"),
            }

    def execute_compensation(
        self,
        dfid: str,
        action: CompensationAction,
    ) -> CompensationResult:
        """
        Execute deterministic compensation. Callbacks are domain-specific.
        ALERT_HUMAN triggers escalation callback.
        """
        state = self.get_dirty_state(dfid)
        if not state:
            return CompensationResult(
                success=False, message="Flow not in dirty state"
            )

        if action == CompensationAction.NOOP:
            return CompensationResult(success=True, message="NOOP")

        if action == CompensationAction.REVERT:
            if self.revert_callback:
                ok = self.revert_callback(dfid, state["partial_state"])
                if ok:
                    self._clear_dirty(dfid)
                return CompensationResult(success=ok, message="REVERT")
            return CompensationResult(
                success=False, message="No revert callback"
            )

        if action == CompensationAction.CLOSE_ALL:
            if self.close_all_callback:
                ok = self.close_all_callback(dfid)
                if ok:
                    self._clear_dirty(dfid)
                return CompensationResult(success=ok, message="CLOSE_ALL")
            return CompensationResult(
                success=False, message="No close_all callback"
            )

        if action == CompensationAction.ALERT_HUMAN:
            if self.alert_human_callback:
                self.alert_human_callback(dfid, state["partial_state"])
                return CompensationResult(success=True, message="ALERT_HUMAN")
            return CompensationResult(
                success=False, message="No alert_human callback"
            )

        return CompensationResult(
            success=False, message=f"Unknown action: {action}"
        )

    def _clear_dirty(self, dfid: str) -> None:
        """Remove flow from dirty state after successful compensation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM saga_dirty_state WHERE dfid = ?", (dfid,))
            conn.commit()
