"""
dir_repo.py — PostgreSQL storage backends for DIR (sample 08).

Implements every DIR storage Protocol from dir_core.storage.base against one
shared psycopg2 connection.  DDL is applied once via apply_schema() before
constructing backends.

USAGE
-----
    from dir_repo import Repository, connect, apply_schema, build_repository

    conn = connect(config["database"])
    apply_schema(conn)
    repo: Repository = build_repository(conn)

    registry = AgentRegistry(storage=repo.agent_registry, supported_versions="1.x")
    store    = ContextStore(storage=repo.context)

DEPENDENCY
----------
    pip install psycopg2-binary
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.errors
import psycopg2.extensions

from dir_core.storage import StorageBundle

# One PostgreSQL repository exposes every DIR storage role.  Same type as
# dir_core.storage.StorageBundle — the alias is for readability at call sites.
Repository = StorageBundle

_SCHEMA_PATH = Path(__file__).parent / "pg_schema.sql"

# Each CREATE TABLE statement in schema.sql (psycopg2: one command per execute).
_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+\w+\s*\([\s\S]+?\);\s*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def connect(cfg: Dict[str, Any]) -> psycopg2.extensions.connection:
    """Open a psycopg2 connection from a config dict.

    Expected keys: host, port, dbname, user, password.
    All keys are passed as keyword arguments to psycopg2.connect; additional
    keys (e.g. sslmode, connect_timeout) are forwarded transparently.
    """
    return psycopg2.connect(**cfg)


def apply_schema(conn: psycopg2.extensions.connection) -> None:
    """Execute schema.sql against *conn* (CREATE TABLE IF NOT EXISTS — idempotent).

    Call once on startup before constructing storage instances.
    Statements are executed one at a time (psycopg2 requires a single SQL
    command per execute()).
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [m.group(0).strip() for m in _CREATE_TABLE_RE.finditer(sql)]
    if not statements:
        raise RuntimeError(
            f"No CREATE TABLE statements found in {_SCHEMA_PATH}"
        )
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def build_repository(
    conn: psycopg2.extensions.connection,
) -> Repository:
    """Return a repository handle with every storage backend backed by *conn*."""
    return StorageBundle(
        agent_registry=PgAgentRegistryStorage(conn),
        context=PgContextStorage(conn),
        idempotency=PgIdempotencyStorage(conn),
        decision_audit=PgDecisionAuditStorage(conn),
        saga=PgSagaStorage(conn),
        resource_lock=PgResourceLockStorage(conn),
        intent_retry=PgIntentRetryStorage(conn),
        escalation=PgEscalationStorage(conn),
        lifecycle=PgLifecycleStorage(conn),
    )


# ---------------------------------------------------------------------------
# DIR §2.3 — Agent Registry storage
# ---------------------------------------------------------------------------


class PgAgentRegistryStorage:
    """PostgreSQL backend for AgentRegistry (DIR §2.3).

    Table: agent_registry  (see schema.sql)
    """

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

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
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_registry
                    (agent_id, contract, priority, status,
                     agent_version, session_token)
                VALUES (%s, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT (agent_id) DO UPDATE SET
                    contract      = EXCLUDED.contract,
                    priority      = EXCLUDED.priority,
                    status        = EXCLUDED.status,
                    agent_version = EXCLUDED.agent_version,
                    session_token = EXCLUDED.session_token,
                    updated_at    = NOW()
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
        self._conn.commit()

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT agent_id, contract::text, priority, status,
                       agent_version, session_token
                FROM   agent_registry
                WHERE  agent_id = %s
                """,
                (agent_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "agent_id":      row[0],
            "contract":      json.loads(row[1]) if row[1] else {},
            "priority":      row[2],
            "status":        row[3],
            "agent_version": row[4],
            "session_token": row[5],
        }

    def update_status(
        self,
        agent_id: str,
        status: str,
        suspension_reason: Optional[str],
    ) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_registry
                SET    status            = %s,
                       suspension_reason = %s,
                       updated_at        = NOW()
                WHERE  agent_id = %s
                """,
                (status, suspension_reason, agent_id),
            )
            changed = cur.rowcount > 0
        self._conn.commit()
        return changed

    def get_status(self, agent_id: str) -> Optional[Tuple[str, Optional[str]]]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT status, suspension_reason "
                "FROM   agent_registry WHERE agent_id = %s",
                (agent_id,),
            )
            row = cur.fetchone()
        return (row[0], row[1]) if row else None

    def list_active_agents(self) -> List[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT agent_id FROM agent_registry WHERE status = 'ACTIVE'"
            )
            rows = cur.fetchall()
        return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# DIR §8 — Context storage
# ---------------------------------------------------------------------------


class PgContextStorage:
    """PostgreSQL backend for ContextStore (DIR §8).

    Tables: context_session, context_state  (see schema.sql)
    """

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def init_schema(self) -> None:
        pass

    def get_session(self, dfid: str) -> Optional[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT data::text FROM context_session WHERE dfid = %s",
                (dfid,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def set_session(self, dfid: str, data_json: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO context_session (dfid, data)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (dfid) DO UPDATE SET
                    data       = EXCLUDED.data,
                    updated_at = NOW()
                """,
                (dfid, data_json),
            )
        self._conn.commit()

    def get_state(self, agent_id: str) -> Optional[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT data::text FROM context_state WHERE agent_id = %s",
                (agent_id,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def set_state(self, agent_id: str, data_json: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO context_state (agent_id, data)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (agent_id) DO UPDATE SET
                    data       = EXCLUDED.data,
                    version    = context_state.version + 1,
                    updated_at = NOW()
                """,
                (agent_id, data_json),
            )
        self._conn.commit()


# ---------------------------------------------------------------------------
# DIR §7 — Idempotency
# ---------------------------------------------------------------------------


class PgIdempotencyStorage:
    """PostgreSQL backend for IdempotencyGuard (DIR §7)."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT result::text FROM idempotency_cache WHERE key = %s",
                (key,),
            )
            row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return json.loads(row[0])

    def set(self, key: str, result: Dict[str, Any]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO idempotency_cache (key, result)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (key) DO UPDATE SET
                    result     = EXCLUDED.result,
                    created_at = NOW()
                """,
                (key, json.dumps(result)),
            )
        self._conn.commit()


# ---------------------------------------------------------------------------
# Observability — decision audit events
# ---------------------------------------------------------------------------


class PgDecisionAuditStorage:
    """PostgreSQL backend for decision_audit_events."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

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
    ) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO decision_audit_events
                    (dfid, event, timestamp, step_id, state, detail_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (dfid, event, ts, step_id, state, json.dumps(details or {})),
            )
        self._conn.commit()

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT dfid, event, timestamp, step_id, state, detail_json::text
                FROM decision_audit_events
                WHERE dfid = %s
                ORDER BY id ASC
                """,
                (dfid,),
            )
            rows = cur.fetchall()
        return [
            {
                "dfid": r[0],
                "event": r[1],
                "timestamp": r[2],
                "step_id": r[3],
                "state": r[4],
                "details": json.loads(r[5] or "{}"),
            }
            for r in rows
        ]

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT dfid, event, timestamp, step_id, state, detail_json::text
                FROM decision_audit_events
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
        return [
            {
                "dfid": r[0],
                "event": r[1],
                "timestamp": r[2],
                "step_id": r[3],
                "state": r[4],
                "details": json.loads(r[5] or "{}"),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# DIR §7 — Saga
# ---------------------------------------------------------------------------


class PgSagaStorage:
    """PostgreSQL backend for SagaCompensation (DIR §7)."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def init_schema(self) -> None:
        pass

    def mark_dirty(
        self, dfid: str, failed_step: str, partial_state_json: str
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO saga_dirty_state
                    (dfid, failed_step, partial_state_json)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (dfid) DO UPDATE SET
                    failed_step        = EXCLUDED.failed_step,
                    partial_state_json = EXCLUDED.partial_state_json,
                    created_at         = NOW()
                """,
                (dfid, failed_step, partial_state_json),
            )
        self._conn.commit()

    def get_dirty_flows(self) -> List[str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT dfid FROM saga_dirty_state")
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def get_dirty_state(self, dfid: str) -> Optional[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT failed_step, partial_state_json::text "
                "FROM saga_dirty_state WHERE dfid = %s",
                (dfid,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "failed_step": row[0],
            "partial_state": json.loads(row[1] or "{}"),
        }

    def clear_dirty(self, dfid: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM saga_dirty_state WHERE dfid = %s", (dfid,)
            )
        self._conn.commit()


# ---------------------------------------------------------------------------
# DIR §6.2 — Resource locks
# ---------------------------------------------------------------------------


class PgResourceLockStorage:
    """PostgreSQL backend for ResourceLockManager (DIR §6.2).

    acquire_batch uses LOCK TABLE ... EXCLUSIVE MODE with lock_timeout and
    retries, so concurrent batch writes serialize (reference pattern for samples).
    """

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def init_schema(self) -> None:
        pass

    def get_locked_amount(self, resource_id: str, exclude_dfid: str) -> float:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM resource_locks "
                "WHERE resource_id = %s AND dfid != %s",
                (resource_id, exclude_dfid),
            )
            row = cur.fetchone()
        return float(row[0]) if row else 0.0

    def acquire_batch(
        self,
        dfid: str,
        resources: Dict[str, float],
        timeout_sec: float,
    ) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SET LOCAL lock_timeout = '100ms'")
                    cur.execute(
                        "LOCK TABLE resource_locks IN EXCLUSIVE MODE"
                    )
                    for rid, amount in resources.items():
                        cur.execute(
                            """
                            INSERT INTO resource_locks
                                (dfid, resource_id, amount)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (dfid, resource_id) DO UPDATE SET
                                amount = EXCLUDED.amount,
                                acquired_at = NOW()
                            """,
                            (dfid, rid, amount),
                        )
                self._conn.commit()
                return True
            except psycopg2.errors.LockNotAvailable:
                self._conn.rollback()
            except psycopg2.OperationalError as e:
                self._conn.rollback()
                if getattr(e, "pgcode", None) != "55P03":
                    raise
            time.sleep(0.05)
        return False

    def release(self, dfid: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM resource_locks WHERE dfid = %s", (dfid,)
            )
        self._conn.commit()


# ---------------------------------------------------------------------------
# DIR §6.2 — Intent retry
# ---------------------------------------------------------------------------


class PgIntentRetryStorage:
    """PostgreSQL backend for IntentRetryGovernor (DIR §6.2)."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def get_count(self, dfid: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT rejection_count FROM intent_retry WHERE dfid = %s",
                (dfid,),
            )
            row = cur.fetchone()
        return row[0] if row else 0

    def set_count(self, dfid: str, count: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO intent_retry (dfid, rejection_count)
                VALUES (%s, %s)
                ON CONFLICT (dfid) DO UPDATE SET
                    rejection_count = EXCLUDED.rejection_count,
                    updated_at = NOW()
                """,
                (dfid, count),
            )
        self._conn.commit()

    def delete(self, dfid: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM intent_retry WHERE dfid = %s", (dfid,))
        self._conn.commit()


# ---------------------------------------------------------------------------
# DIR §9 — Escalation
# ---------------------------------------------------------------------------


class PgEscalationStorage:
    """PostgreSQL backend for EscalationManager (DIR §9)."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def init_schema(self) -> None:
        pass

    def get_window_count(self, agent_id: str, since_str: str) -> int:
        # since_str is naive UTC from EscalationManager — compare as timestamptz.
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM escalation_budget
                WHERE agent_id = %s
                  AND created_at >= (%s::timestamp AT TIME ZONE 'UTC')
                """,
                (agent_id, since_str),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def record_budget_token(self, agent_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO escalation_budget (agent_id) VALUES (%s)",
                (agent_id,),
            )
        self._conn.commit()

    def insert_request(
        self,
        dfid: str,
        agent_id: str,
        reason: str,
        context_json: str,
        proposal_json: str,
        impact: str,
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO escalation_requests
                    (dfid, agent_id, reason, context_json, proposal_json,
                     impact, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
                ON CONFLICT (dfid) DO UPDATE SET
                    agent_id      = EXCLUDED.agent_id,
                    reason        = EXCLUDED.reason,
                    context_json  = EXCLUDED.context_json,
                    proposal_json = EXCLUDED.proposal_json,
                    impact        = EXCLUDED.impact,
                    status        = 'PENDING',
                    created_at    = NOW(),
                    resolved_at   = NULL,
                    human_decision = NULL
                """,
                (dfid, agent_id, reason, context_json, proposal_json, impact),
            )
        self._conn.commit()

    def resolve_request(
        self,
        dfid: str,
        resolved_at: str,
        decision: str,
        proposal_json: Optional[str],
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE escalation_requests
                SET status = 'RESOLVED',
                    resolved_at = %s::timestamptz,
                    human_decision = %s,
                    proposal_json = COALESCE(%s, proposal_json)
                WHERE dfid = %s
                """,
                (resolved_at, decision, proposal_json, dfid),
            )
        self._conn.commit()

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT dfid, agent_id, reason, context_json, proposal_json, impact
                FROM escalation_requests
                WHERE status = 'PENDING'
                """
            )
            rows = cur.fetchall()
        return [
            {
                "dfid":     r[0],
                "agent_id": r[1],
                "reason":   r[2],
                "context":  json.loads(r[3] or "{}"),
                "proposal": json.loads(r[4] or "{}"),
                "impact":   r[5],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# DIR §4.3 — Lifecycle
# ---------------------------------------------------------------------------


class PgLifecycleStorage:
    """PostgreSQL backend for lifecycle transitions (DIR §4.3)."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def record_transition(
        self, dfid: str, from_status: str, to_status: str
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO flow_transitions (dfid, from_status, to_status)
                VALUES (%s, %s, %s)
                """,
                (dfid, from_status, to_status),
            )
        self._conn.commit()
