"""
Context Store (DIR §8) - Manages multi-layered context for agents.

Layers:
1. Session (Ephemeral): Context specific to the current DecisionFlow (dfid).
2. State (Authoritative): Long-lived agent state (policy versions, trajectory).
3. Memory (Long-term): Vector DB or archival storage (Stub for MVP).
4. Artifacts (Reference): Static docs/rules (Stub).

Provides `compile_working_context` to assemble a frozen view for decision making.
"""

import json
import sqlite3
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ContextStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Ensure tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Session: Linked to DFID
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_session (
                    dfid TEXT PRIMARY KEY,
                    data JSON,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # State: Linked to Agent ID
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_state (
                    agent_id TEXT PRIMARY KEY,
                    data JSON,
                    version INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # Layer 1: Session (Ephemeral)
    # -------------------------------------------------------------------------

    def get_session(self, dfid: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT data FROM context_session WHERE dfid = ?", (dfid,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else {}

    def update_session(self, dfid: str, updates: Dict[str, Any]) -> None:
        """Merge updates into existing session."""
        current = self.get_session(dfid)
        current.update(updates)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO context_session (dfid, data) VALUES (?, ?)",
                (dfid, json.dumps(current))
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # Layer 2: State (Authoritative)
    # -------------------------------------------------------------------------

    def get_state(self, agent_id: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT data FROM context_state WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else {}

    def update_state(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """Merge updates into existing state."""
        current = self.get_state(agent_id)
        current.update(updates)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO context_state (agent_id, data) VALUES (?, ?)",
                (agent_id, json.dumps(current))
            )
            conn.commit()

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
