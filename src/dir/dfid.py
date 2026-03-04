"""
DecisionFlow ID (DFID) – correlation identifier for the full decision lifecycle.

See DIR Architectural Pattern §4. All operations (observation, reasoning, validation,
execution) are tagged with the same DFID for audit and traceability.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


def new_dfid() -> str:
    """Generate a new DecisionFlow ID (UUID v4)."""
    return str(uuid.uuid4())


def new_dfid_with_parent(parent_dfid: str) -> str:
    """Generate a child DFID for hierarchical flows.

    Parent is not encoded in the ID; relationship is stored in context/ledger.
    Parent DFID is logged for traceability.
    """
    child_id = str(uuid.uuid4())
    logger.debug("Child DFID %s created with parent %s", child_id[:8], parent_dfid[:8])
    return child_id
