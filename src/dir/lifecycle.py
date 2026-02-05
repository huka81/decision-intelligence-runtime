"""
DecisionFlow lifecycle: CREATED -> ACTIVE -> VALIDATING -> ACCEPTED|ABORTED|ESCALATED -> EXECUTING -> CLOSED.

DIR §4.3, §9. Stub for MVP; implement when building samples 9 and 13.
"""

from enum import Enum
from typing import Optional


class FlowStatus(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    VALIDATING = "VALIDATING"
    ACCEPTED = "ACCEPTED"
    ABORTED = "ABORTED"
    ESCALATED = "ESCALATED"
    EXECUTING = "EXECUTING"
    CLOSED = "CLOSED"


def transition(dfid: str, from_status: FlowStatus, to_status: FlowStatus) -> None:
    """Record transition. Stub: no-op."""
    pass
