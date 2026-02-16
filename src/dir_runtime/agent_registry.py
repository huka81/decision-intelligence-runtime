"""
Agent Registry: manifest, handshake, lookup by agent_id.

DIR §2.3. Maintains a registry of active agents, their capabilities, and metadata.
"""

import json
import sqlite3
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentRegistry:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_registry (
                    agent_id TEXT PRIMARY KEY,
                    manifest JSON,
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ACTIVE',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def register_agent(
        self, 
        agent_id: str, 
        manifest: Dict[str, Any], 
        priority: int = 0
    ) -> None:
        """Register or update an agent."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_registry (agent_id, manifest, priority, status)
                VALUES (?, ?, ?, 'ACTIVE')
                """,
                (agent_id, json.dumps(manifest), priority)
            )
            conn.commit()
        logger.info(f"Registered agent: {agent_id} (priority={priority})")

    def get_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent manifest."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT manifest FROM agent_registry WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def get_agent_priority(self, agent_id: str) -> int:
        """Retrieve agent priority (default 0)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT priority FROM agent_registry WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            return row[0] if row else 0

    def list_agents(self) -> List[str]:
        """List all active agent IDs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT agent_id FROM agent_registry WHERE status = 'ACTIVE'")
            return [row[0] for row in cursor.fetchall()]
