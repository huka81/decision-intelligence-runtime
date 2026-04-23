"""
SQLite storage backends for dir_core modules.

These are the default built-in implementations used when ``db_path`` is
provided to any manager class.  They require no additional dependencies
(``sqlite3`` is part of the Python standard library).

The canonical database schema lives in ``schema.sql`` (same directory).
All ``init_schema`` calls load and apply that file — no DDL is hardcoded here.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..data_types import AgentRegistryStatus

from .json_util import dumps_json_dict

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection, creating parent directories if needed."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


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
                "SELECT data FROM context_session WHERE dfid = ?", (dfid,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_session(self, dfid: str, data_json: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO context_session (dfid, data) "
                "VALUES (?, ?)",
                (dfid, data_json),
            )
            conn.commit()

    def get_state(self, agent_id: str) -> Optional[str]:
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM context_state WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_state(self, agent_id: str, data_json: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO context_state (agent_id, data) "
                "VALUES (?, ?)",
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
                "SELECT result FROM idempotency_cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def set(self, key: str, result: Dict[str, Any]) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO idempotency_cache (key, result) "
                "VALUES (?, ?)",
                (key, dumps_json_dict(result)),
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
    ) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        payload = dumps_json_dict(details or {})
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO decision_audit_events
                    (dfid, event, timestamp, step_id, state, detail_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (dfid, event, ts, step_id, state, payload),
            )
            conn.commit()

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, event, timestamp, step_id, state, detail_json
                FROM decision_audit_events
                WHERE dfid = ?
                ORDER BY id ASC
                """,
                (dfid,),
            )
            rows = cursor.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "dfid": r["dfid"],
                    "event": r["event"],
                    "timestamp": r["timestamp"],
                    "step_id": r["step_id"],
                    "state": r["state"],
                    "details": json.loads(r["detail_json"] or "{}"),
                }
            )
        return out

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, event, timestamp, step_id, state, detail_json
                FROM decision_audit_events
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "dfid": r["dfid"],
                    "event": r["event"],
                    "timestamp": r["timestamp"],
                    "step_id": r["step_id"],
                    "state": r["state"],
                    "details": json.loads(r["detail_json"] or "{}"),
                }
            )
        return out


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
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for rid, amount in resources.items():
                        conn.execute(
                            "INSERT OR REPLACE INTO resource_locks "
                            "(dfid, resource_id, amount) VALUES (?, ?, ?)",
                            (dfid, rid, amount),
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
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO escalation_requests
                (dfid, agent_id, reason, context_json, proposal_json,
                 impact, status)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (dfid, agent_id, reason, context_json, proposal_json, impact),
            )
            conn.commit()

    def resolve_request(
        self,
        dfid: str,
        resolved_at: str,
        decision: str,
        proposal_json: Optional[str],
    ) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE escalation_requests
                SET status = 'RESOLVED', resolved_at = ?,
                    human_decision = ?,
                    proposal_json = COALESCE(?, proposal_json)
                WHERE dfid = ?
                """,
                (resolved_at, decision, proposal_json, dfid),
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
        self, dfid: str, from_status: str, to_status: str
    ) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO flow_transitions (dfid, from_status, to_status) "
                "VALUES (?, ?, ?)",
                (dfid, from_status, to_status),
            )
            conn.commit()
