"""
Context Store (DIR §8) - Manages multi-layered context for agents.

Layers:
1. Session (Ephemeral): Context specific to the current DecisionFlow (dfid).
2. State (Authoritative): Long-lived agent state (policy versions, trajectory).
3. Memory (Long-term): Vector DB or archival storage (Stub for MVP).
4. Artifacts (Reference): Static docs/rules (Stub).

Provides `compile_working_context` to assemble a frozen view for decision making.

Implementation note: Memory and Artifacts layers are stubs (return {}).
Full implementation requires: Memory (vector DB / archival), Artifacts (RAG / static docs).
See DIR §8.1, ROA §7.2 for layer definitions.
"""

import json
import logging
from typing import Any, Dict, Optional

from .storage.base import ContextStorage
from .storage.sqlite import SqliteContextStorage

logger = logging.getLogger(__name__)


class ContextStore:
    """Multi-layered context store for agent state (DIR §8).

    Storage backend is pluggable. Pass ``storage=`` for a custom backend, or
    ``db_path=`` to use the built-in SQLite backend (default behaviour).

    Args:
        db_path: Path to SQLite database. Used when ``storage`` is not provided.
        storage: Custom :class:`~dir_core.storage.ContextStorage` backend.
            When provided, ``db_path`` is ignored.

    Raises:
        ValueError: When neither ``db_path`` nor ``storage`` is supplied.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        storage: Optional[ContextStorage] = None,
    ):
        if storage is not None:
            self._storage: ContextStorage = storage
        elif db_path is not None:
            self.db_path = db_path  # kept for backward compatibility
            self._storage = SqliteContextStorage(db_path)
        else:
            raise ValueError(
                "Provide either 'db_path' (SQLite) or 'storage' (custom backend)."
            )

    # -------------------------------------------------------------------------
    # Layer 1: Session (Ephemeral)
    # -------------------------------------------------------------------------

    def get_session(self, dfid: str) -> Dict[str, Any]:
        raw = self._storage.get_session(dfid)
        return json.loads(raw) if raw else {}

    def update_session(self, dfid: str, updates: Dict[str, Any]) -> None:
        """Merge updates into existing session."""
        current = self.get_session(dfid)
        current.update(updates)
        self._storage.set_session(dfid, json.dumps(current))

    # -------------------------------------------------------------------------
    # Layer 2: State (Authoritative)
    # -------------------------------------------------------------------------

    def get_state(self, agent_id: str) -> Dict[str, Any]:
        raw = self._storage.get_state(agent_id)
        return json.loads(raw) if raw else {}

    def update_state(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """Merge updates into existing state."""
        current = self.get_state(agent_id)
        current.update(updates)
        self._storage.set_state(agent_id, json.dumps(current))

    # -------------------------------------------------------------------------
    # Compiler
    # -------------------------------------------------------------------------

    def compile_working_context(self, agent_id: str, dfid: str) -> Dict[str, Any]:
        """
        Assemble all layers into a single Working Context.
        Returns immutable dictionary (snapshot).
        """
        session_data = self.get_session(dfid)
        state_data = self.get_state(agent_id)

        # In a real system, we'd fetch Memory and Artifacts here too.

        return {
            "meta": {
                "agent_id": agent_id,
                "dfid": dfid,
                "source": "ContextStore",
            },
            "session": session_data,
            "state": state_data,
            "memory": {},    # Stub
            "artifacts": {}  # Stub
        }
