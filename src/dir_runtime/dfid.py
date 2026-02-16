"""
DecisionFlow ID (DFID) – correlation identifier for the full decision lifecycle.

See DIR Architectural Pattern §4. All operations (observation, reasoning, validation,
execution) are tagged with the same DFID for audit and traceability.
"""

import uuid
from typing import Optional


def new_dfid() -> str:
    """Generate a new DecisionFlow ID (UUID v4)."""
    return str(uuid.uuid4())


def new_dfid_with_parent(parent_dfid: str) -> str:
    """Generate a child DFID for hierarchical flows. Parent is not encoded in the ID;
    relationship is stored in context/ledger."""
    return str(uuid.uuid4())
