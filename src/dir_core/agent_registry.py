"""
Agent Registry: contract, handshake, lookup by agent_id.

DIR §2.3. Maintains a registry of active agents, their capability contracts, and metadata.
Handshake with SemVer alignment; schema serving for Context compilation.
"""

import json
import re
import uuid
import logging
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .data_types import AgentRegistryStatus, HandshakeRejectionReason
from .storage.base import AgentRegistryStorage
from .storage.sqlite import SqliteAgentRegistryStorage

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
    """Registry of active agents with SemVer handshake (DIR §2.3).

    Storage backend is pluggable. Pass ``storage=`` for a custom backend, or
    ``db_path=`` to use the built-in SQLite backend (default behaviour).

    Args:
        db_path: Path to SQLite database. Used when ``storage`` is not provided.
        supported_versions: SemVer constraint for handshake (e.g. ``"1.x"``).
        storage: Custom :class:`~dir_core.storage.AgentRegistryStorage` backend.
            When provided, ``db_path`` is ignored.

    Raises:
        ValueError: When neither ``db_path`` nor ``storage`` is supplied.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        supported_versions: str = "1.x",
        *,
        storage: Optional[AgentRegistryStorage] = None,
    ):
        self.supported_versions = supported_versions
        if storage is not None:
            self._storage: AgentRegistryStorage = storage
        elif db_path is not None:
            self.db_path = db_path  # kept for backward compatibility
            self._storage = SqliteAgentRegistryStorage(db_path)
        else:
            raise ValueError(
                "Provide either 'db_path' (SQLite) or 'storage' (custom backend)."
            )

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
                reason=HandshakeRejectionReason.VERSION_MISMATCH.value,
            )
        token = str(uuid.uuid4())
        self._storage.upsert_agent(
            agent_id=agent_id,
            contract_json=json.dumps(contract),
            priority=priority,
            status=AgentRegistryStatus.ACTIVE,
            agent_version=agent_version,
            session_token=token,
        )
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
        self._storage.upsert_agent(
            agent_id=agent_id,
            contract_json=json.dumps(contract),
            priority=priority,
            status=AgentRegistryStatus.ACTIVE,
            agent_version=None,
            session_token=None,
        )
        logger.info("Registered agent: %s (priority=%d)", agent_id, priority)

    def get_agent_contract(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent capability contract."""
        rec = self._storage.get_agent(agent_id)
        return rec["contract"] if rec else None

    def get_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent capability contract. Deprecated: use get_agent_contract."""
        return self.get_agent_contract(agent_id)

    def get_agent_priority(self, agent_id: str) -> int:
        """Retrieve agent priority (default 0)."""
        rec = self._storage.get_agent(agent_id)
        return rec["priority"] if rec else 0

    def list_agents(self) -> List[str]:
        """List all active agent IDs."""
        return self._storage.list_active_agents()

    def set_agent_status(
        self,
        agent_id: str,
        status: str,
        suspension_reason: Optional[str] = None,
    ) -> bool:
        """
        Transition agent lifecycle status (e.g. ACTIVE -> SUSPENDED).

        Args:
            agent_id: Registered agent identifier.
            status: New status value (e.g. 'SUSPENDED', 'ACTIVE').
            suspension_reason: Optional machine-oriented reason (audit / ops).

        Returns:
            True if a row was updated.
        """
        updated = self._storage.update_status(agent_id, status, suspension_reason)
        if updated:
            logger.info(
                "Agent status: agent_id=%s status=%s reason=%s",
                agent_id,
                status,
                suspension_reason,
            )
        return updated

    def get_agent_status(self, agent_id: str) -> Optional[tuple]:
        """Return (status, suspension_reason) if the agent exists, else None."""
        return self._storage.get_status(agent_id)
