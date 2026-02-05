"""
Decision Integrity Module (DIM): schema + RBAC + optional state check.

DIR §6. Validates PolicyProposal; returns ACCEPT or REJECT with reason code.
Stub for MVP; implement when building samples 5 and 9.
"""

from typing import Literal, Tuple

from .models import PolicyProposal

ValidationResult = Tuple[Literal["ACCEPT", "REJECT"], str]


def validate(proposal: PolicyProposal) -> ValidationResult:
    """Validate proposal. Stub: always ACCEPT."""
    return "ACCEPT", "OK"
