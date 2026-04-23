"""
Storage Protocols for dir_core modules (DIR §2.3, §6.2, §7, §8, §9).

Implement any Protocol to create a custom storage backend (PostgreSQL, Redis,
CSV, cloud KV store, etc.). Pass the instance via the ``storage=`` kwarg of the
corresponding manager class.

For JSON columns (audit ``details``, idempotency ``result``), implementations
should use :func:`~dir_core.storage.json_util.dumps_json_dict` so custom
backends match the built-in SQLite and sample PostgreSQL encodings.

Example — custom PostgreSQL backend for AgentRegistry::

    class MyPgAgentStorage:
        def init_schema(self) -> None: ...
        def upsert_agent(self, agent_id, contract_json, priority, status,
                         agent_version, session_token) -> None: ...
        ...  # implement remaining methods

    registry = AgentRegistry(storage=MyPgAgentStorage(...))
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


class StorageError(Exception):
    """Base exception raised by storage backends."""


class ResourceContentionError(StorageError):
    """Raised when an exclusive lock cannot be acquired within the timeout."""


# ---------------------------------------------------------------------------
# Agent Registry (DIR §2.3)
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentRegistryStorage(Protocol):
    def init_schema(self) -> None:
        """Create or migrate the underlying schema (called once on construction)."""
        ...

    def upsert_agent(
        self,
        agent_id: str,
        contract_json: str,
        priority: int,
        status: str,
        agent_version: Optional[str],
        session_token: Optional[str],
    ) -> None:
        """Insert or replace an agent record."""
        ...

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return a dict with keys agent_id/contract/priority/status/
        agent_version/session_token, or None if not found."""
        ...

    def update_status(
        self, agent_id: str, status: str, suspension_reason: Optional[str]
    ) -> bool:
        """Update status and suspension_reason. Return True if a row was changed."""
        ...

    def get_status(self, agent_id: str) -> Optional[Tuple[str, Optional[str]]]:
        """Return (status, suspension_reason) or None if agent does not exist."""
        ...

    def list_active_agents(self) -> List[str]:
        """Return agent_ids where status == 'ACTIVE'."""
        ...


# ---------------------------------------------------------------------------
# Context Store (DIR §8)
# ---------------------------------------------------------------------------


@runtime_checkable
class ContextStorage(Protocol):
    def init_schema(self) -> None: ...

    def get_session(self, dfid: str) -> Optional[str]:
        """Return JSON-encoded session data for dfid, or None."""
        ...

    def set_session(self, dfid: str, data_json: str) -> None:
        """Persist JSON-encoded session data for dfid."""
        ...

    def get_state(self, agent_id: str) -> Optional[str]:
        """Return JSON-encoded state for agent_id, or None."""
        ...

    def set_state(self, agent_id: str, data_json: str) -> None:
        """Persist JSON-encoded state for agent_id."""
        ...


# ---------------------------------------------------------------------------
# Idempotency (DIR §7)
# ---------------------------------------------------------------------------


@runtime_checkable
class IdempotencyStorage(Protocol):
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return cached result for key, or None on cache miss."""
        ...

    def set(self, key: str, result: Dict[str, Any]) -> None:
        """Store result under key.

        Implementations SHOULD persist JSON with the same encoding rules as
        :func:`~dir_core.storage.json_util.dumps_json_dict` (stable key order,
        ``default=str``) so disk backends stay interchangeable.
        """
        ...


# ---------------------------------------------------------------------------
# Decision audit trail (core data model: decision_audit_events + idempotency_cache)
# ---------------------------------------------------------------------------


@runtime_checkable
class DecisionAuditStorage(Protocol):
    def init_schema(self) -> None: ...

    def record(
        self,
        dfid: str,
        event: str,
        *,
        step_id: str = "",
        state: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append one DFID-scoped audit row.

        *details* is persisted as JSON. Implementations MUST use the same
        encoding as :func:`~dir_core.storage.json_util.dumps_json_dict`
        (``sort_keys=True``, ``default=str``) so SQLite, PostgreSQL, and any
        other backend produce comparable ``detail_json`` / ``detail_json``-text
        column values and do not fail on non-JSON-native values.
        """
        ...

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        """Return events for *dfid* in insertion order (details = dict per row)."""
        ...

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        """Return all events in insertion order."""
        ...


class AuditStore:
    """Repository helper: append-only audit rows plus idempotent replay (DIR §7).

    Combines :class:`DecisionAuditStorage` (``decision_audit_events``) and
    :class:`IdempotencyStorage` (``idempotency_cache``). Construct from a
    :class:`~dir_core.storage.StorageBundle` as
    ``AuditStore(bundle.decision_audit, bundle.idempotency)``.
    """

    __slots__ = ("_decision_audit", "_idempotency")

    def __init__(
        self,
        decision_audit: DecisionAuditStorage,
        idempotency: IdempotencyStorage,
    ) -> None:
        self._decision_audit = decision_audit
        self._idempotency = idempotency

    def close(self) -> None:
        """No-op when backends use short-lived connections per call."""
        return None

    def record(
        self,
        dfid: str,
        event: str,
        *,
        step_id: str = "",
        state: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._decision_audit.record(
            dfid, event, step_id=step_id, state=state, details=details
        )

    def get_idempotent_result(self, key: str) -> Optional[Dict[str, Any]]:
        return self._idempotency.get(key)

    def save_idempotent_result(
        self, key: str, dfid: str, result: Dict[str, Any]
    ) -> None:
        payload = dict(result)
        payload["_dfid"] = dfid
        self._idempotency.set(key, payload)

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        return self._decision_audit.events_for_dfid(dfid)

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        return self._decision_audit.all_events_chronological()


# ---------------------------------------------------------------------------
# Saga Compensation (DIR §7, Topologies §6.4)
# ---------------------------------------------------------------------------


@runtime_checkable
class SagaStorage(Protocol):
    def init_schema(self) -> None: ...

    def mark_dirty(self, dfid: str, failed_step: str, partial_state_json: str) -> None:
        """Record dfid as PARTIAL_SUCCESS_DIRTY with the given state snapshot."""
        ...

    def get_dirty_flows(self) -> List[str]:
        """Return all dfids currently in dirty state."""
        ...

    def get_dirty_state(self, dfid: str) -> Optional[Dict[str, Any]]:
        """Return dict with 'failed_step' and 'partial_state' keys, or None."""
        ...

    def clear_dirty(self, dfid: str) -> None:
        """Remove dfid from dirty state after successful compensation."""
        ...


# ---------------------------------------------------------------------------
# Resource Locking (DIR §6.2)
# ---------------------------------------------------------------------------


@runtime_checkable
class ResourceLockStorage(Protocol):
    def init_schema(self) -> None: ...

    def get_locked_amount(self, resource_id: str, exclude_dfid: str) -> float:
        """Return the total reserved amount for resource_id, excluding
        any lock already held by exclude_dfid (so re-acquiring is idempotent).
        """
        ...

    def acquire_batch(
        self,
        dfid: str,
        resources: Dict[str, float],
        timeout_sec: float,
    ) -> bool:
        """Atomically write all locks for dfid.

        The availability check is performed by :class:`ResourceLockManager`
        *before* calling this method.  Implementations must ensure the write
        is atomic so that two concurrent callers cannot both see "enough room"
        and both succeed.

        Args:
            dfid: Flow identifier claiming the locks.
            resources: Mapping of resource_id -> requested amount.
            timeout_sec: Maximum time to wait for exclusive write access.

        Returns:
            ``True`` if all locks were written, ``False`` if exclusive access
            could not be obtained within *timeout_sec*
            (``RESOURCE_CONTENTION_TIMEOUT``).

        Note:
            Implementations that guarantee atomic check-and-set (e.g. a
            Postgres ``INSERT ... WHERE available - locked >= requested``)
            may perform the availability check themselves and raise
            :exc:`InsufficientCapacityError` when capacity is exceeded.
        """
        ...

    def release(self, dfid: str) -> None:
        """Release all locks held by dfid."""
        ...


# ---------------------------------------------------------------------------
# Intent Retry Governor (DIR §6.2)
# ---------------------------------------------------------------------------


@runtime_checkable
class IntentRetryStorage(Protocol):
    def get_count(self, dfid: str) -> int:
        """Return current rejection count for dfid (0 if unseen)."""
        ...

    def set_count(self, dfid: str, count: int) -> None:
        """Persist rejection count for dfid."""
        ...

    def delete(self, dfid: str) -> None:
        """Remove dfid record (called when flow reaches terminal state)."""
        ...


# ---------------------------------------------------------------------------
# Escalation Manager (DIR §9)
# ---------------------------------------------------------------------------


@runtime_checkable
class EscalationStorage(Protocol):
    def init_schema(self) -> None: ...

    def get_window_count(self, agent_id: str, since_str: str) -> int:
        """Count budget tokens for agent_id after since_str (ISO/SQLite timestamp)."""
        ...

    def record_budget_token(self, agent_id: str) -> None:
        """Record one escalation token consumption for agent_id."""
        ...

    def insert_request(
        self,
        dfid: str,
        agent_id: str,
        reason: str,
        context_json: str,
        proposal_json: str,
        impact: str,
    ) -> None:
        """Persist a new escalation request with PENDING status."""
        ...

    def resolve_request(
        self,
        dfid: str,
        resolved_at: str,
        decision: str,
        proposal_json: Optional[str],
    ) -> None:
        """Mark escalation as RESOLVED with human decision."""
        ...

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Return list of pending requests as dicts with
        dfid/agent_id/reason/context/proposal/impact keys."""
        ...


# ---------------------------------------------------------------------------
# Lifecycle (DIR §4.3)
# ---------------------------------------------------------------------------


@runtime_checkable
class LifecycleStorage(Protocol):
    def record_transition(
        self, dfid: str, from_status: str, to_status: str
    ) -> None:
        """Append a flow transition record."""
        ...
