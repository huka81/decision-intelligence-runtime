"""
DecisionFlow lifecycle: CREATED -> ACTIVE -> VALIDATING -> ACCEPTED|ABORTED|ESCALATED -> EXECUTING -> CLOSED.

DIR §4.3, §9. Persists transitions; resets IntentRetryGovernor on terminal states.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .intent_retry import IntentRetryGovernor
    from .storage.base import LifecycleStorage


class FlowStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    VALIDATING = "VALIDATING"
    ACCEPTED = "ACCEPTED"
    ABORTED = "ABORTED"
    ESCALATED = "ESCALATED"
    EXECUTING = "EXECUTING"
    CLOSED = "CLOSED"
    # Saga (DIR §7, Topologies §6.4)
    PARTIAL_SUCCESS_DIRTY = "PARTIAL_SUCCESS_DIRTY"
    MAINTENANCE_MODE = "MAINTENANCE_MODE"


def transition(
    dfid: str,
    from_status: FlowStatus,
    to_status: FlowStatus,
    retry_governor: Optional["IntentRetryGovernor"] = None,
    db_path: Optional[str] = None,
    *,
    storage: Optional["LifecycleStorage"] = None,
    root_dfid: Optional[str] = None,
) -> None:
    """Record a flow status transition.

    On CLOSED/ABORTED, resets the retry governor for dfid.

    Args:
        dfid: DecisionFlow identifier.
        from_status: Current status.
        to_status: Target status.
        retry_governor: Optional governor to reset on terminal transitions.
        db_path: SQLite path for persistence (legacy kwarg). When ``storage``
            is also provided, ``storage`` takes precedence.
        storage: Custom :class:`~dir_core.storage.LifecycleStorage` backend.
            Pass ``None`` to skip persistence entirely.
        root_dfid: Top-level flow id for ``flow_transitions``; defaults to *dfid*.
    """
    if retry_governor is not None and to_status in (FlowStatus.CLOSED, FlowStatus.ABORTED):
        retry_governor.reset(dfid)

    _storage = storage
    if _storage is None and db_path is not None:
        from .storage.sqlite import SqliteLifecycleStorage
        _storage = SqliteLifecycleStorage(db_path)

    if _storage is not None:
        _storage.record_transition(
            dfid,
            from_status.value,
            to_status.value,
            root_dfid=root_dfid,
        )
