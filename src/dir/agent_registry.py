"""
Agent Registry: manifest, handshake, lookup by agent_id.

DIR §2.3. Stub for MVP; implement when building samples 6 and 9.
"""

from typing import Any, Dict, List

# In-memory or SQLite-backed registry of agent_id -> manifest (version, capabilities, mission_ref).


def register(agent_id: str, manifest: Dict[str, Any]) -> None:
    """Register agent manifest. Stub: no-op."""
    pass


def get_manifest(agent_id: str) -> Dict[str, Any] | None:
    """Lookup manifest by agent_id. Stub: returns None."""
    return None


def get_priority(agent_id: str) -> int:
    """Priority for EOAM preemption. Stub: returns 0."""
    return 0
