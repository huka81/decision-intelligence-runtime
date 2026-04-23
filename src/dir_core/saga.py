"""
Saga Compensation (DIR §7, Topologies §6.4).

Parent-Child flows: mark_dirty on partial failure, deterministic compensation.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .models import CompensationAction
from .storage.base import SagaStorage
from .storage.sqlite import SqliteSagaStorage

logger = logging.getLogger(__name__)


@dataclass
class CompensationResult:
    """Result of execute_compensation."""

    success: bool
    message: str = ""


class SagaCompensation:
    """Manages dirty state and deterministic compensation (DIR §7).

    Storage backend is pluggable. Pass ``storage=`` for a custom backend, or
    ``db_path=`` to use the built-in SQLite backend (default behaviour).

    Args:
        db_path: Path to SQLite database. Used when ``storage`` is not provided.
        revert_callback: Called with (dfid, partial_state) on REVERT.
        close_all_callback: Called with (dfid,) on CLOSE_ALL.
        alert_human_callback: Called with (dfid, partial_state) on ALERT_HUMAN.
        storage: Custom :class:`~dir_core.storage.SagaStorage` backend.
            When provided, ``db_path`` is ignored.

    Raises:
        ValueError: When neither ``db_path`` nor ``storage`` is supplied.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        revert_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        close_all_callback: Optional[Callable[[str], bool]] = None,
        alert_human_callback: Optional[
            Callable[[str, Dict[str, Any]], None]
        ] = None,
        *,
        storage: Optional[SagaStorage] = None,
    ):
        self.revert_callback = revert_callback
        self.close_all_callback = close_all_callback
        self.alert_human_callback = alert_human_callback

        if storage is not None:
            self._storage: SagaStorage = storage
        elif db_path is not None:
            self.db_path = db_path  # kept for backward compatibility
            self._storage = SqliteSagaStorage(db_path)
        else:
            raise ValueError(
                "Provide either 'db_path' (SQLite) or 'storage' (custom backend)."
            )

    def mark_dirty(
        self,
        dfid: str,
        failed_step: str,
        partial_state: Dict[str, Any],
    ) -> None:
        """Record flow as PARTIAL_SUCCESS_DIRTY after step failure."""
        self._storage.mark_dirty(
            dfid, failed_step, json.dumps(partial_state, default=str)
        )
        logger.warning("Saga dirty: dfid=%s failed_step=%s", dfid, failed_step)

    def get_dirty_flows(self) -> List[str]:
        """Return list of dfids in dirty state."""
        return self._storage.get_dirty_flows()

    def get_dirty_state(self, dfid: str) -> Optional[Dict[str, Any]]:
        """Return partial state for dirty flow."""
        return self._storage.get_dirty_state(dfid)

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
        self._storage.clear_dirty(dfid)
