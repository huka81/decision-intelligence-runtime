"""
In-memory storage backends for dir_core modules.

No persistence — data lives only in process memory.
Ideal for unit tests and scenarios where durability is not required.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..data_types import AgentRegistryStatus


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------


class MemoryAgentRegistryStorage:
    """In-memory backend for AgentRegistry."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def init_schema(self) -> None:
        pass

    def upsert_agent(
        self,
        agent_id: str,
        contract_json: str,
        priority: int,
        status: str,
        agent_version: Optional[str],
        session_token: Optional[str],
    ) -> None:
        suspension_reason = self._store.get(agent_id, {}).get("suspension_reason")
        self._store[agent_id] = {
            "agent_id": agent_id,
            "contract": json.loads(contract_json) if contract_json else {},
            "priority": priority,
            "status": status,
            "agent_version": agent_version,
            "session_token": session_token,
            "suspension_reason": suspension_reason,
        }

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(agent_id)

    def update_status(
        self, agent_id: str, status: str, suspension_reason: Optional[str]
    ) -> bool:
        if agent_id not in self._store:
            return False
        self._store[agent_id]["status"] = status
        self._store[agent_id]["suspension_reason"] = suspension_reason
        return True

    def get_status(self, agent_id: str) -> Optional[Tuple[str, Optional[str]]]:
        rec = self._store.get(agent_id)
        if rec is None:
            return None
        return (rec["status"], rec.get("suspension_reason"))

    def list_active_agents(self) -> List[str]:
        return [
            aid
            for aid, rec in self._store.items()
            if rec.get("status") == AgentRegistryStatus.ACTIVE
        ]


# ---------------------------------------------------------------------------
# Context Store
# ---------------------------------------------------------------------------


class MemoryContextStorage:
    """In-memory backend for ContextStore."""

    def __init__(self) -> None:
        self._sessions: Dict[str, str] = {}
        self._states: Dict[str, str] = {}

    def init_schema(self) -> None:
        pass

    def get_session(self, dfid: str) -> Optional[str]:
        return self._sessions.get(dfid)

    def set_session(
        self, dfid: str, data_json: str, *, agent_id: Optional[str] = None
    ) -> None:
        del agent_id  # in-memory backend does not model decision_flows FK
        self._sessions[dfid] = data_json

    def get_state(self, agent_id: str) -> Optional[str]:
        return self._states.get(agent_id)

    def set_state(self, agent_id: str, data_json: str) -> None:
        self._states[agent_id] = data_json


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class MemoryIdempotencyStorage:
    """In-memory backend for IdempotencyGuard."""

    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set(self, key: str, result: Any) -> None:
        self._cache[key] = result


# ---------------------------------------------------------------------------
# Decision audit trail
# ---------------------------------------------------------------------------


class MemoryDecisionAuditStorage:
    """In-memory backend for DFID-scoped decision audit rows."""

    def __init__(self) -> None:
        self._rows: List[Dict[str, Any]] = []

    def init_schema(self) -> None:
        pass

    def record(
        self,
        dfid: str,
        event: str,
        *,
        step_id: str = "",
        state: str = "",
        details: Optional[Dict[str, Any]] = None,
        root_dfid: Optional[str] = None,
        agent_id: Optional[str] = None,
        severity: str = "INFO",
    ) -> None:
        del agent_id  # optional; persisted only by SQL backends
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        rd = root_dfid or dfid
        self._rows.append(
            {
                "dfid": dfid,
                "root_dfid": rd,
                "event": event,
                "event_type": event,
                "timestamp": ts,
                "created_at": ts,
                "severity": severity,
                "step_id": step_id,
                "state": state,
                "details": dict(details or {}),
            }
        )

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows if r["dfid"] == dfid]

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows]


# ---------------------------------------------------------------------------
# Decision Ledger (Topology C / DL+PCI)
# ---------------------------------------------------------------------------


class MemoryDecisionLedgerStorage:
    """In-memory backend for verified PCI ledger entries."""

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []

    def init_schema(self) -> None:
        pass

    def append(
        self,
        pci: Any,
        *,
        agent_id: str,
        root_dfid: Optional[str] = None,
    ) -> None:
        rd = root_dfid or pci.dfid
        if any(e["dfid"] == pci.dfid for e in self._entries):
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self._entries.append(
            {
                "dfid": pci.dfid,
                "root_dfid": rd,
                "agent_id": agent_id,
                "intent_payload": dict(pci.intent_payload),
                "context_ref": pci.context_ref,
                "evidence_hash": pci.evidence_hash,
                "signature": pci.signature or "",
                "committed_at": ts,
            }
        )

    def get_by_dfid(self, dfid: str) -> Optional[Dict[str, Any]]:
        for entry in self._entries:
            if entry["dfid"] == dfid:
                return dict(entry)
        return None

    def entries_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        entry = self.get_by_dfid(dfid)
        return [entry] if entry else []

    def all_entries_chronological(self) -> List[Dict[str, Any]]:
        return [dict(e) for e in self._entries]


# ---------------------------------------------------------------------------
# Saga
# ---------------------------------------------------------------------------


class MemorySagaStorage:
    """In-memory backend for SagaCompensation."""

    def __init__(self) -> None:
        self._dirty: Dict[str, Dict[str, Any]] = {}

    def init_schema(self) -> None:
        pass

    def mark_dirty(self, dfid: str, failed_step: str, partial_state_json: str) -> None:
        self._dirty[dfid] = {
            "failed_step": failed_step,
            "partial_state": json.loads(partial_state_json or "{}"),
        }

    def get_dirty_flows(self) -> List[str]:
        return list(self._dirty.keys())

    def get_dirty_state(self, dfid: str) -> Optional[Dict[str, Any]]:
        return self._dirty.get(dfid)

    def clear_dirty(self, dfid: str) -> None:
        self._dirty.pop(dfid, None)


# ---------------------------------------------------------------------------
# Resource Locking
# ---------------------------------------------------------------------------


class MemoryResourceLockStorage:
    """In-memory backend for ResourceLockManager.

    Thread-safe via a reentrant lock.
    """

    def __init__(self) -> None:
        self._locks: Dict[str, Dict[str, float]] = {}
        self._mutex = threading.Lock()

    def init_schema(self) -> None:
        pass

    def get_locked_amount(self, resource_id: str, exclude_dfid: str) -> float:
        """Return total locked amount for resource_id (excluding exclude_dfid)."""
        with self._mutex:
            return sum(
                locks.get(resource_id, 0.0)
                for d, locks in self._locks.items()
                if d != exclude_dfid
            )

    def acquire_batch(
        self,
        dfid: str,
        resources: Dict[str, float],
        timeout_sec: float,
    ) -> bool:
        with self._mutex:
            self._locks[dfid] = dict(resources)
            return True

    def release(self, dfid: str) -> None:
        with self._mutex:
            self._locks.pop(dfid, None)


# ---------------------------------------------------------------------------
# Intent Retry
# ---------------------------------------------------------------------------


class MemoryIntentRetryStorage:
    """In-memory backend for IntentRetryGovernor."""

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}

    def get_count(self, dfid: str) -> int:
        return self._counts.get(dfid, 0)

    def set_count(self, dfid: str, count: int) -> None:
        self._counts[dfid] = count

    def delete(self, dfid: str) -> None:
        self._counts.pop(dfid, None)


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


class MemoryEscalationStorage:
    """In-memory backend for EscalationManager."""

    def __init__(self) -> None:
        self._budget: List[Dict[str, Any]] = []
        self._requests: Dict[str, Dict[str, Any]] = {}

    def init_schema(self) -> None:
        pass

    def get_window_count(self, agent_id: str, since_str: str) -> int:
        since = datetime.fromisoformat(since_str.replace(" ", "T"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        return sum(
            1
            for e in self._budget
            if e["agent_id"] == agent_id and e["created_at"] >= since
        )

    def record_budget_token(self, agent_id: str) -> None:
        self._budget.append(
            {"agent_id": agent_id, "created_at": datetime.now(timezone.utc)}
        )

    def insert_request(
        self,
        dfid: str,
        agent_id: str,
        reason: str,
        context_json: str,
        proposal_json: str,
        impact: str,
    ) -> None:
        self._requests[dfid] = {
            "dfid": dfid,
            "root_dfid": dfid,
            "agent_id": agent_id,
            "reason": reason,
            "context": json.loads(context_json or "{}"),
            "proposal": json.loads(proposal_json or "{}"),
            "impact": impact,
            "status": "PENDING",
            "resolved_at": None,
            "human_decision": None,
        }

    def resolve_request(
        self,
        dfid: str,
        resolved_at: str,
        decision: str,
        proposal_json: Optional[str],
    ) -> None:
        if dfid in self._requests:
            req = self._requests[dfid]
            u = (decision or "").upper()
            req["status"] = "REJECTED" if u == "ABORT" else "APPROVED"
            req["resolved_at"] = resolved_at
            req["human_decision"] = decision
            if proposal_json:
                req["proposal"] = json.loads(proposal_json)

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        return [
            {
                "dfid": req["dfid"],
                "agent_id": req["agent_id"],
                "reason": req["reason"],
                "context": req["context"],
                "proposal": req["proposal"],
                "impact": req["impact"],
            }
            for req in self._requests.values()
            if req["status"] == "PENDING"
        ]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class MemoryLifecycleStorage:
    """In-memory backend for lifecycle.transition."""

    def __init__(self) -> None:
        self._transitions: List[Dict[str, Any]] = []

    def record_transition(
        self,
        dfid: str,
        from_status: str,
        to_status: str,
        *,
        root_dfid: Optional[str] = None,
    ) -> None:
        rd = root_dfid or dfid
        self._transitions.append(
            {
                "dfid": dfid,
                "root_dfid": rd,
                "from_status": from_status,
                "to_status": to_status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_transitions(self, dfid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Helper: return all transitions, optionally filtered by dfid."""
        if dfid is None:
            return list(self._transitions)
        return [t for t in self._transitions if t["dfid"] == dfid]
