"""
SQLite storage backends for dir_core modules.

These are the default built-in implementations used when ``db_path`` is
provided to any manager class.  They require no additional dependencies
(``sqlite3`` is part of the Python standard library).

The canonical database schema lives in ``schema.sql`` (same directory).
All ``init_schema`` calls load and apply that file — no DDL is hardcoded here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..data_types import AgentRegistryStatus

from .json_util import dumps_json_dict

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_DIR_KERNEL_AGENT = "__dir_kernel__"
_IDEMPOTENCY_TTL_DAYS = 365

_AUDIT_SEVERITIES = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection, creating parent directories if needed."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_agent_registry_row(conn: sqlite3.Connection, agent_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO agent_registry (agent_id, contract, priority, status) "
        "VALUES (?, '{}', 0, 'ACTIVE')",
        (agent_id,),
    )


def _ensure_root_decision_flow(
    conn: sqlite3.Connection, dfid: str, agent_id: str
) -> None:
    _ensure_agent_registry_row(conn, agent_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO decision_flows
            (dfid, root_dfid, dfid_parent, agent_id, status)
        VALUES (?, ?, NULL, ?, 'CREATED')
        """,
        (dfid, dfid, agent_id),
    )


def _ensure_decision_flow_for_dfid(
    conn: sqlite3.Connection,
    dfid: str,
    *,
    agent_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    aid = agent_id or (details or {}).get("agent_id")
    if aid:
        _ensure_root_decision_flow(conn, dfid, aid)
    else:
        _ensure_root_decision_flow(conn, dfid, _DIR_KERNEL_AGENT)


def _idempotency_expires_iso() -> str:
    return (
        datetime.now(timezone.utc) + timedelta(days=_IDEMPOTENCY_TTL_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _request_hash(payload: Dict[str, Any]) -> str:
    body = dumps_json_dict(payload)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _human_decision_to_escalation_status(decision: str) -> str:
    u = (decision or "").upper()
    if u == "ABORT":
        return "REJECTED"
    return "APPROVED"


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Execute every DDL statement from ``schema.sql`` against *conn*.

    Uses ``executescript`` so that semicolons inside SQL comments do not
    cause false statement splits.
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)


def ensure_db(
    path: Path | str,
    create_tables: Optional[Callable[[sqlite3.Connection], None]] = None,
) -> Path:
    """Create parent dirs and an empty DB file if needed, then run optional schema callback.

    Used by samples that need SQLite before wiring storage backends.  Returns
    the resolved :class:`~pathlib.Path` to the database file.
    """
    resolved = Path(path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if create_tables is not None:
            create_tables(conn)
        conn.commit()
    finally:
        conn.close()
    return resolved


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------


class SqliteAgentRegistryStorage:
    """SQLite backend for AgentRegistry (DIR §2.3)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def upsert_agent(
        self,
        agent_id: str,
        contract_json: str,
        priority: int,
        status: str,
        agent_version: Optional[str],
        session_token: Optional[str],
    ) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_registry
                (agent_id, contract, priority, status, agent_version, session_token)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    contract_json,
                    priority,
                    status,
                    agent_version,
                    session_token,
                ),
            )
            conn.commit()

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT agent_id, contract, priority, status, agent_version, "
                "session_token FROM agent_registry WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "agent_id": row[0],
                "contract": json.loads(row[1]) if row[1] else {},
                "priority": row[2],
                "status": row[3],
                "agent_version": row[4],
                "session_token": row[5],
            }

    def update_status(
        self, agent_id: str, status: str, suspension_reason: Optional[str]
    ) -> bool:
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE agent_registry
                SET status = ?, suspension_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = ?
                """,
                (status, suspension_reason, agent_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_status(self, agent_id: str) -> Optional[Tuple[str, Optional[str]]]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT status, suspension_reason "
                "FROM agent_registry WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            return (row[0], row[1]) if row else None

    def list_active_agents(self) -> List[str]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT agent_id FROM agent_registry WHERE status = ?",
                (AgentRegistryStatus.ACTIVE,),
            )
            return [row[0] for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Context Store
# ---------------------------------------------------------------------------


class SqliteContextStorage:
    """SQLite backend for ContextStore (DIR §8)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def get_session(self, dfid: str) -> Optional[str]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM flow_context WHERE dfid = ?", (dfid,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_session(self, dfid: str, data_json: str, *, agent_id: Optional[str] = None) -> None:
        with _connect(self.db_path) as conn:
            eff_agent = agent_id or _DIR_KERNEL_AGENT
            _ensure_root_decision_flow(conn, dfid, eff_agent)
            conn.execute(
                """
                INSERT INTO flow_context (dfid, data, version, updated_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(dfid) DO UPDATE SET
                    data = excluded.data,
                    version = flow_context.version + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (dfid, data_json),
            )
            conn.commit()

    def get_state(self, agent_id: str) -> Optional[str]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM agent_state WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_state(self, agent_id: str, data_json: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agent_state (agent_id, data, version, updated_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id) DO UPDATE SET
                    data = excluded.data,
                    version = agent_state.version + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (agent_id, data_json),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class SqliteIdempotencyStorage:
    """SQLite backend for IdempotencyGuard (DIR §7)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT result FROM idempotency_cache WHERE idempotency_key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def set(self, key: str, result: Dict[str, Any]) -> None:
        payload = dumps_json_dict(result)
        rh = _request_hash(result)
        exp = _idempotency_expires_iso()
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO idempotency_cache
                    (idempotency_key, request_hash, result, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    request_hash = excluded.request_hash,
                    result = excluded.result,
                    created_at = CURRENT_TIMESTAMP,
                    expires_at = excluded.expires_at
                """,
                (key, rh, payload, exp),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Decision audit trail
# ---------------------------------------------------------------------------


class SqliteDecisionAuditStorage:
    """SQLite backend for append-only decision_audit_events."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

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
        rd = root_dfid or dfid
        sev = severity if severity in _AUDIT_SEVERITIES else "INFO"
        payload = dumps_json_dict(details or {})
        with _connect(self.db_path) as conn:
            _ensure_decision_flow_for_dfid(conn, dfid, agent_id=agent_id, details=details)
            conn.execute(
                """
                INSERT INTO decision_audit_events
                    (dfid, root_dfid, event_type, severity, step_id, state, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (dfid, rd, event, sev, step_id, state, payload),
            )
            conn.commit()

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> Dict[str, Any]:
        detail = json.loads(r["detail_json"] or "{}")
        created = r["created_at"]
        et = r["event_type"]
        return {
            "dfid": r["dfid"],
            "root_dfid": r["root_dfid"],
            "event": et,
            "event_type": et,
            "timestamp": created,
            "created_at": created,
            "severity": r["severity"],
            "step_id": r["step_id"],
            "state": r["state"],
            "details": detail,
        }

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, root_dfid, event_type, severity, step_id, state,
                       detail_json, created_at
                FROM decision_audit_events
                WHERE dfid = ?
                ORDER BY id ASC
                """,
                (dfid,),
            )
            rows = cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, root_dfid, event_type, severity, step_id, state,
                       detail_json, created_at
                FROM decision_audit_events
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()
        return [self._row_to_event(r) for r in rows]


# ---------------------------------------------------------------------------
# Decision Ledger (Topology C / DL+PCI)
# ---------------------------------------------------------------------------


class SqliteDecisionLedgerStorage:
    """SQLite backend for append-only decision_ledger_entries."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    @staticmethod
    def _row_to_entry(r: sqlite3.Row) -> Dict[str, Any]:
        return {
            "dfid": r["dfid"],
            "root_dfid": r["root_dfid"],
            "agent_id": r["agent_id"],
            "intent_payload": json.loads(r["intent_payload"] or "{}"),
            "context_ref": r["context_ref"],
            "evidence_hash": r["evidence_hash"],
            "signature": r["signature"],
            "committed_at": r["committed_at"],
        }

    def append(
        self,
        pci: Any,
        *,
        agent_id: str,
        root_dfid: Optional[str] = None,
    ) -> None:
        rd = root_dfid or pci.dfid
        payload = dumps_json_dict(pci.intent_payload)
        with _connect(self.db_path) as conn:
            _ensure_decision_flow_for_dfid(conn, pci.dfid, agent_id=agent_id)
            conn.execute(
                """
                INSERT OR IGNORE INTO decision_ledger_entries
                    (dfid, root_dfid, agent_id, intent_payload, context_ref,
                     evidence_hash, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pci.dfid,
                    rd,
                    agent_id,
                    payload,
                    pci.context_ref,
                    pci.evidence_hash,
                    pci.signature or "",
                ),
            )
            conn.commit()

    def get_by_dfid(self, dfid: str) -> Optional[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, root_dfid, agent_id, intent_payload, context_ref,
                       evidence_hash, signature, committed_at
                FROM decision_ledger_entries
                WHERE dfid = ?
                """,
                (dfid,),
            )
            row = cursor.fetchone()
        return self._row_to_entry(row) if row else None

    def entries_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        entry = self.get_by_dfid(dfid)
        return [entry] if entry else []

    def all_entries_chronological(self) -> List[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, root_dfid, agent_id, intent_payload, context_ref,
                       evidence_hash, signature, committed_at
                FROM decision_ledger_entries
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()
        return [self._row_to_entry(r) for r in rows]


# ---------------------------------------------------------------------------
# Saga
# ---------------------------------------------------------------------------


class SqliteSagaStorage:
    """SQLite backend for SagaCompensation (DIR §7)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def mark_dirty(
        self, dfid: str, failed_step: str, partial_state_json: str
    ) -> None:
        with _connect(self.db_path) as conn:
            _ensure_root_decision_flow(conn, dfid, _DIR_KERNEL_AGENT)
            conn.execute(
                """
                INSERT OR REPLACE INTO saga_dirty_state
                (dfid, failed_step, partial_state_json) VALUES (?, ?, ?)
                """,
                (dfid, failed_step, partial_state_json),
            )
            conn.commit()

    def get_dirty_flows(self) -> List[str]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute("SELECT dfid FROM saga_dirty_state")
            return [row[0] for row in cursor.fetchall()]

    def get_dirty_state(self, dfid: str) -> Optional[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT failed_step, partial_state_json "
                "FROM saga_dirty_state WHERE dfid = ?",
                (dfid,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "failed_step": row[0],
                "partial_state": json.loads(row[1] or "{}"),
            }

    def clear_dirty(self, dfid: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM saga_dirty_state WHERE dfid = ?", (dfid,)
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Resource Locking
# ---------------------------------------------------------------------------


class SqliteResourceLockStorage:
    """SQLite backend for ResourceLockManager (DIR §6.2).

    ``acquire_batch`` uses ``BEGIN IMMEDIATE`` to guarantee that the
    check-and-insert performed by :class:`ResourceLockManager` is not
    interleaved with another concurrent ``acquire_batch``.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def get_locked_amount(self, resource_id: str, exclude_dfid: str) -> float:
        """Return total locked amount for resource_id (excluding exclude_dfid)."""
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM resource_locks "
                "WHERE resource_id = ? AND dfid != ?",
                (resource_id, exclude_dfid),
            )
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0

    def acquire_batch(
        self,
        dfid: str,
        resources: Dict[str, float],
        timeout_sec: float,
    ) -> bool:
        """Atomically write all locks using ``BEGIN IMMEDIATE``.

        Returns True if written, False if contention persisted beyond timeout.
        """
        deadline = time.monotonic() + timeout_sec

        while time.monotonic() < deadline:
            try:
                conn = sqlite3.connect(self.db_path, timeout=0.1)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _ensure_root_decision_flow(conn, dfid, _DIR_KERNEL_AGENT)
                    for rid, amount in resources.items():
                        conn.execute(
                            "INSERT OR REPLACE INTO resource_locks "
                            "(resource_id, dfid, amount) VALUES (?, ?, ?)",
                            (rid, dfid, amount),
                        )
                    conn.commit()
                    conn.close()
                    return True
                except Exception:
                    conn.rollback()
                    conn.close()
                    raise
            except sqlite3.OperationalError:
                time.sleep(0.05)
                continue

        return False

    def release(self, dfid: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM resource_locks WHERE dfid = ?", (dfid,)
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Intent Retry
# ---------------------------------------------------------------------------


class SqliteIntentRetryStorage:
    """SQLite backend for IntentRetryGovernor (DIR §6.2)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def get_count(self, dfid: str) -> int:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT rejection_count FROM intent_retry WHERE dfid = ?",
                (dfid,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def set_count(self, dfid: str, count: int) -> None:
        with _connect(self.db_path) as conn:
            _ensure_root_decision_flow(conn, dfid, _DIR_KERNEL_AGENT)
            conn.execute(
                "INSERT OR REPLACE INTO intent_retry "
                "(dfid, rejection_count, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (dfid, count),
            )
            conn.commit()

    def delete(self, dfid: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("DELETE FROM intent_retry WHERE dfid = ?", (dfid,))
            conn.commit()


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


class SqliteEscalationStorage:
    """SQLite backend for EscalationManager (DIR §9)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def get_window_count(self, agent_id: str, since_str: str) -> int:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM escalation_budget "
                "WHERE agent_id = ? AND created_at >= ?",
                (agent_id, since_str),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def record_budget_token(self, agent_id: str) -> None:
        with _connect(self.db_path) as conn:
            _ensure_agent_registry_row(conn, agent_id)
            conn.execute(
                "INSERT INTO escalation_budget (agent_id) VALUES (?)",
                (agent_id,),
            )
            conn.commit()

    def insert_request(
        self,
        dfid: str,
        agent_id: str,
        reason: str,
        context_json: str,
        proposal_json: str,
        impact: str,
    ) -> None:
        root_dfid = dfid
        with _connect(self.db_path) as conn:
            _ensure_root_decision_flow(conn, dfid, agent_id)
            conn.execute(
                """
                INSERT INTO escalation_requests
                (dfid, root_dfid, agent_id, reason, context_json, proposal_json,
                 impact, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    dfid,
                    root_dfid,
                    agent_id,
                    reason,
                    context_json,
                    proposal_json,
                    impact,
                ),
            )
            conn.commit()

    def resolve_request(
        self,
        dfid: str,
        resolved_at: str,
        decision: str,
        proposal_json: Optional[str],
    ) -> None:
        status = _human_decision_to_escalation_status(decision)
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE escalation_requests
                SET status = ?, resolved_at = ?,
                    human_decision = ?,
                    proposal_json = COALESCE(?, proposal_json)
                WHERE dfid = ? AND status = 'PENDING'
                """,
                (status, resolved_at, decision, proposal_json, dfid),
            )
            conn.commit()

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT dfid, agent_id, reason, context_json, "
                "proposal_json, impact "
                "FROM escalation_requests WHERE status = 'PENDING'"
            )
            rows = cursor.fetchall()
            return [
                {
                    "dfid": r["dfid"],
                    "agent_id": r["agent_id"],
                    "reason": r["reason"],
                    "context": json.loads(r["context_json"] or "{}"),
                    "proposal": json.loads(r["proposal_json"] or "{}"),
                    "impact": r["impact"],
                }
                for r in rows
            ]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class SqliteLifecycleStorage:
    """SQLite backend for lifecycle.transition (DIR §4.3)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.init_schema()

    def init_schema(self) -> None:
        with _connect(self.db_path) as conn:
            _apply_schema(conn)

    def record_transition(
        self,
        dfid: str,
        from_status: str,
        to_status: str,
        *,
        root_dfid: Optional[str] = None,
    ) -> None:
        rd = root_dfid or dfid
        with _connect(self.db_path) as conn:
            _ensure_root_decision_flow(conn, dfid, _DIR_KERNEL_AGENT)
            conn.execute(
                "INSERT INTO flow_transitions (dfid, root_dfid, from_status, to_status) "
                "VALUES (?, ?, ?, ?)",
                (dfid, rd, from_status, to_status),
            )
            conn.commit()
