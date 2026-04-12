"""
In-memory storage backends for dir_core modules.

No persistence — data lives only in process memory.
Ideal for unit tests and scenarios where durability is not required.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


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

    def get_status(self, agent_id: str) -> Optional[tuple]:
        rec = self._store.get(agent_id)
        if rec is None:
            return None
        return (rec["status"], rec.get("suspension_reason"))

    def list_active_agents(self) -> List[str]:
        return [
            aid for aid, rec in self._store.items() if rec.get("status") == "ACTIVE"
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

    def set_session(self, dfid: str, data_json: str) -> None:
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

    Thread-safe via a reentrant lock; no retry delay needed.
    """

    def __init__(self) -> None:
        self._locks: Dict[str, Dict[str, float]] = {}
        self._mutex = threading.Lock()

    def init_schema(self) -> None:
        pass

    def try_acquire_atomic(
        self,
        dfid: str,
        resources: Dict[str, float],
        availability_provider: Callable[[str], float],
        timeout_sec: float,
    ) -> str:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            with self._mutex:
                for rid, amount in resources.items():
                    available = availability_provider(rid)
                    locked = sum(
                        locks.get(rid, 0.0)
                        for d, locks in self._locks.items()
                        if d != dfid
                    )
                    if available - locked < amount:
                        return "INSUFFICIENT_LIQUIDITY"
                self._locks[dfid] = dict(resources)
                return "ACQUIRED"
        return "RESOURCE_CONTENTION_TIMEOUT"

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
            req["status"] = "RESOLVED"
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

    def record_transition(self, dfid: str, from_status: str, to_status: str) -> None:
        self._transitions.append(
            {
                "dfid": dfid,
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
