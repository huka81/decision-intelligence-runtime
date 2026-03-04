"""
DecisionFlow lifecycle: CREATED -> ACTIVE -> VALIDATING -> ACCEPTED|ABORTED|ESCALATED -> EXECUTING -> CLOSED.

DIR §4.3, §9. Persists transitions; resets IntentRetryGovernor on terminal states.
"""

from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .intent_retry import IntentRetryGovernor


class FlowStatus(str, Enum):
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
) -> None:
    """Record transition. On CLOSED/ABORTED, resets retry governor for dfid."""
    if retry_governor is not None and to_status in (FlowStatus.CLOSED, FlowStatus.ABORTED):
        retry_governor.reset(dfid)
    if db_path:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS flow_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dfid TEXT, from_status TEXT, to_status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO flow_transitions (dfid, from_status, to_status) VALUES (?, ?, ?)",
                (dfid, from_status.value, to_status.value),
            )
            conn.commit()
