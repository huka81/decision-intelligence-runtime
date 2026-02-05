"""
Context Store: four layers (Session, State, Memory, Artifacts) and compile_working_context.

ROA §7, DIR §8. Stub for MVP; implement when building samples 4 and 9.
"""

from typing import Any, Dict

# Stub: compile_working_context(agent_id, dfid) -> WorkingContext
# Will use bootstrap_sqlite and tables per layer.


def compile_working_context(agent_id: str, dfid: str) -> Dict[str, Any]:
    """Return immutable working context for agent. Stub: returns minimal dict."""
    return {
        "agent_id": agent_id,
        "dfid": dfid,
        "snapshot_id": None,
        "session": [],
        "state": {},
        "memory": [],
        "artifacts_refs": [],
    }
