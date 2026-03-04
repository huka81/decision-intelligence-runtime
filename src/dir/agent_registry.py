"""
Agent Registry: contract, handshake, lookup by agent_id.

DIR §2.3. Maintains a registry of active agents, their capability contracts, and metadata.
Handshake with SemVer alignment; schema serving for Context compilation.
"""

import json
import re
import sqlite3
import uuid
import logging
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")


@dataclass
class HandshakeResult:
    """Result of agent handshake (DIR §2.3)."""

    accepted: bool
    session_token: Optional[str] = None
    reason: Optional[str] = None


def _parse_version(v: str) -> Optional[tuple]:
    """Parse semver string to (major, minor, patch)."""
    m = SEMVER_RE.match(v.strip())
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return (major, minor, patch)


def _version_compatible(agent_ver: str, supported: str) -> bool:
    """
    Check if agent_ver is compatible with supported (e.g. "1.x" or "1.2").
    """
    av = _parse_version(agent_ver)
    if not av:
        return False
    if supported.endswith(".x"):
        prefix = supported[:-2]
        sv = _parse_version(prefix + ".0")
        if not sv:
            return False
        return av[0] == sv[0]
    sv = _parse_version(supported)
    if not sv:
        return False
    return av[0] == sv[0] and av[1] >= sv[1]


class AgentRegistry:
    def __init__(
        self,
        db_path: str,
        supported_versions: str = "1.x",
    ):
        self.db_path = db_path
        self.supported_versions = supported_versions
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_registry (
                    agent_id TEXT PRIMARY KEY,
                    contract JSON,
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ACTIVE',
                    agent_version TEXT,
                    session_token TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                conn.execute(
                    "ALTER TABLE agent_registry RENAME COLUMN manifest TO contract"
                )
            except sqlite3.OperationalError:
                pass
            for col, spec in [
                ("agent_version", "TEXT"),
                ("session_token", "TEXT"),
                ("registered_at", "TIMESTAMP"),
            ]:
                try:
                    conn.execute(
                        f"ALTER TABLE agent_registry ADD COLUMN {col} {spec}"
                    )
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def handshake(
        self,
        agent_id: str,
        contract: Dict[str, Any],
        agent_version: str,
        priority: int = 0,
    ) -> HandshakeResult:
        """
        Handshake with version check. REJECT on VERSION_MISMATCH.
        Returns ACCEPTED with session_token or REJECTED with reason.
        """
        if not _version_compatible(agent_version, self.supported_versions):
            return HandshakeResult(
                accepted=False,
                reason="VERSION_MISMATCH",
            )
        token = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_registry
                (agent_id, contract, priority, status, agent_version, session_token)
                VALUES (?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (agent_id, json.dumps(contract), priority, agent_version, token),
            )
            conn.commit()
        logger.info("Handshake: agent_id=%s ver=%s accepted", agent_id, agent_version)
        return HandshakeResult(accepted=True, session_token=token)

    def get_schema(
        self, agent_id: str, schema_kind: Optional[str] = None
    ) -> Optional[dict]:
        """Return schema from contract: schema_kind=None -> contract['schema'];
        else -> contract['schemas'][kind] or contract['schema']."""
        contract = self.get_agent_contract(agent_id)
        if not contract:
            return None
        if schema_kind is not None and "schemas" in contract and schema_kind in contract["schemas"]:
            return contract["schemas"][schema_kind]
        return contract.get("schema")

    def register_agent(
        self,
        agent_id: str,
        contract: Dict[str, Any],
        priority: int = 0,
    ) -> None:
        """Register or update an agent with capability contract.

        Deprecated: Use handshake() for version checking and session tokens (DIR §2.3).
        register_agent does not enforce SemVer compatibility.
        """
        warnings.warn(
            "register_agent is deprecated; use handshake() for version checking (DIR §2.3)",
            DeprecationWarning,
            stacklevel=2,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_registry (agent_id, contract, priority, status)
                VALUES (?, ?, ?, 'ACTIVE')
                """,
                (agent_id, json.dumps(contract), priority),
            )
            conn.commit()
        logger.info("Registered agent: %s (priority=%d)", agent_id, priority)

    def get_agent_contract(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent capability contract."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT contract FROM agent_registry WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def get_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent capability contract. Deprecated: use get_agent_contract."""
        return self.get_agent_contract(agent_id)

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
