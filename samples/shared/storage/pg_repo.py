"""
pg_repo.py — PostgreSQL storage backends for DIR (samples 08+).

Implements every DIR storage Protocol from dir_core.storage.base against one
shared psycopg2 connection.  DDL is defined in pg_schema.sql (canonical parity
with src/dir_core/storage/schema.sql) and applied via apply_schema().

USAGE
-----
    from samples.shared.storage.pg_repo import connect, apply_schema, build_repository

    conn = connect(config["database"])
    apply_schema(conn)
    repo = build_repository(conn)

    registry = AgentRegistry(storage=repo.agent_registry, supported_versions="1.x")
    store    = ContextStore(storage=repo.context)

DEPENDENCY
----------
    pip install psycopg2-binary
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.errors
import psycopg2.extensions

from dir_core.storage import StorageBundle
from dir_core.storage.json_util import dumps_json_dict

# One PostgreSQL repository exposes every DIR storage role.  Same type as
# dir_core.storage.StorageBundle — the alias is for readability at call sites.
Repository = StorageBundle

_SCHEMA_PATH = Path(__file__).parent / "pg_schema.sql"

_DIR_KERNEL_AGENT = "__dir_kernel__"
_IDEMPOTENCY_TTL_DAYS = 365

_AUDIT_SEVERITIES = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)

# DDL statements in pg_schema.sql (psycopg2: one command per execute).
_DDL_STMT_RE = re.compile(
    r"CREATE (?:TABLE|INDEX) IF NOT EXISTS\s+[\s\S]+?;\s*",
    re.IGNORECASE,
)


def _ensure_agent_registry_row(
    cur: psycopg2.extensions.cursor, agent_id: str
) -> None:
    cur.execute(
        """
        INSERT INTO agent_registry (agent_id, contract, priority, status)
        VALUES (%s, '{}'::jsonb, 0, 'ACTIVE')
        ON CONFLICT (agent_id) DO NOTHING
        """,
        (agent_id,),
    )


def _ensure_root_decision_flow(
    cur: psycopg2.extensions.cursor, dfid: str, agent_id: str
) -> None:
    _ensure_agent_registry_row(cur, agent_id)
    cur.execute(
        """
        INSERT INTO decision_flows
            (dfid, root_dfid, dfid_parent, agent_id, status)
        VALUES (%s, %s, NULL, %s, 'CREATED')
        ON CONFLICT (dfid) DO NOTHING
        """,
        (dfid, dfid, agent_id),
    )


def _ensure_decision_flow_for_dfid(
    cur: psycopg2.extensions.cursor,
    dfid: str,
    *,
    agent_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    aid = agent_id or (details or {}).get("agent_id")
    if aid:
        _ensure_root_decision_flow(cur, dfid, aid)
    else:
        _ensure_root_decision_flow(cur, dfid, _DIR_KERNEL_AGENT)


def _idempotency_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=_IDEMPOTENCY_TTL_DAYS)


def _request_hash(payload: Dict[str, Any]) -> str:
    body = dumps_json_dict(payload)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _human_decision_to_escalation_status(decision: str) -> str:
    u = (decision or "").upper()
    if u == "ABORT":
        return "REJECTED"
    return "APPROVED"


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
    """Execute pg_schema.sql against *conn* (CREATE TABLE/INDEX — idempotent).

    Call once on startup before constructing storage instances.
    Statements are executed one at a time (psycopg2 requires a single SQL
    command per execute()).
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [m.group(0).strip() for m in _DDL_STMT_RE.finditer(sql)]
    if not statements:
        raise RuntimeError(f"No DDL statements found in {_SCHEMA_PATH}")
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def build_repository(
    conn: psycopg2.extensions.connection,
    *,
    apply_schema_on_build: bool = False,
) -> Repository:
    """Return a repository handle with every storage backend backed by *conn*.

    Set *apply_schema_on_build* when callers skip a separate ``apply_schema()``.
    """
    if apply_schema_on_build:
        apply_schema(conn)
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

    Table: agent_registry  (see pg_schema.sql)
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

    Tables: flow_context, agent_state  (see pg_schema.sql)
    """

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def init_schema(self) -> None:
        pass

    def get_session(self, dfid: str) -> Optional[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT data::text FROM flow_context WHERE dfid = %s",
                (dfid,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def set_session(
        self, dfid: str, data_json: str, *, agent_id: Optional[str] = None
    ) -> None:
        eff_agent = agent_id or _DIR_KERNEL_AGENT
        with self._conn.cursor() as cur:
            _ensure_root_decision_flow(cur, dfid, eff_agent)
            cur.execute(
                """
                INSERT INTO flow_context (dfid, data, version, updated_at)
                VALUES (%s, %s::jsonb, 1, NOW())
                ON CONFLICT (dfid) DO UPDATE SET
                    data       = EXCLUDED.data,
                    version    = flow_context.version + 1,
                    updated_at = NOW()
                """,
                (dfid, data_json),
            )
        self._conn.commit()

    def get_state(self, agent_id: str) -> Optional[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT data::text FROM agent_state WHERE agent_id = %s",
                (agent_id,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def set_state(self, agent_id: str, data_json: str) -> None:
        with self._conn.cursor() as cur:
            _ensure_agent_registry_row(cur, agent_id)
            cur.execute(
                """
                INSERT INTO agent_state (agent_id, data, version, updated_at)
                VALUES (%s, %s::jsonb, 1, NOW())
                ON CONFLICT (agent_id) DO UPDATE SET
                    data       = EXCLUDED.data,
                    version    = agent_state.version + 1,
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
                "SELECT result::text FROM idempotency_cache WHERE idempotency_key = %s",
                (key,),
            )
            row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return json.loads(row[0])

    def set(self, key: str, result: Dict[str, Any]) -> None:
        payload = dumps_json_dict(result)
        rh = _request_hash(result)
        exp = _idempotency_expires_at()
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO idempotency_cache
                    (idempotency_key, request_hash, result, expires_at)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (idempotency_key) DO UPDATE SET
                    request_hash = EXCLUDED.request_hash,
                    result       = EXCLUDED.result,
                    created_at   = NOW(),
                    expires_at   = EXCLUDED.expires_at
                """,
                (key, rh, payload, exp),
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

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> Dict[str, Any]:
        detail = json.loads(row[6] or "{}")
        created = row[7]
        if hasattr(created, "isoformat"):
            created = created.isoformat().replace("+00:00", "Z")
        else:
            created = str(created)
        et = row[2]
        return {
            "dfid": row[0],
            "root_dfid": row[1],
            "event": et,
            "event_type": et,
            "timestamp": created,
            "created_at": created,
            "severity": row[3],
            "step_id": row[4],
            "state": row[5],
            "details": detail,
        }

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
        with self._conn.cursor() as cur:
            _ensure_decision_flow_for_dfid(
                cur, dfid, agent_id=agent_id, details=details
            )
            cur.execute(
                """
                INSERT INTO decision_audit_events
                    (dfid, root_dfid, event_type, severity,
                     step_id, state, detail_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    dfid,
                    rd,
                    event,
                    sev,
                    step_id,
                    state,
                    dumps_json_dict(details or {}),
                ),
            )
        self._conn.commit()

    def events_for_dfid(self, dfid: str) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT dfid, root_dfid, event_type, severity,
                       step_id, state, detail_json::text, created_at
                FROM decision_audit_events
                WHERE dfid = %s
                ORDER BY id ASC
                """,
                (dfid,),
            )
            rows = cur.fetchall()
        return [self._row_to_event(r) for r in rows]

    def all_events_chronological(self) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT dfid, root_dfid, event_type, severity,
                       step_id, state, detail_json::text, created_at
                FROM decision_audit_events
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
        return [self._row_to_event(r) for r in rows]


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
            _ensure_root_decision_flow(cur, dfid, _DIR_KERNEL_AGENT)
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
                    _ensure_root_decision_flow(cur, dfid, _DIR_KERNEL_AGENT)
                    for rid, amount in resources.items():
                        cur.execute(
                            """
                            INSERT INTO resource_locks
                                (resource_id, dfid, amount)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (resource_id) DO UPDATE SET
                                dfid = EXCLUDED.dfid,
                                amount = EXCLUDED.amount,
                                acquired_at = NOW()
                            """,
                            (rid, dfid, amount),
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
            _ensure_root_decision_flow(cur, dfid, _DIR_KERNEL_AGENT)
            cur.execute(
                """
                INSERT INTO intent_retry (dfid, rejection_count, updated_at)
                VALUES (%s, %s, NOW())
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
            _ensure_agent_registry_row(cur, agent_id)
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
        root_dfid = dfid
        with self._conn.cursor() as cur:
            _ensure_root_decision_flow(cur, dfid, agent_id)
            cur.execute(
                """
                INSERT INTO escalation_requests
                    (dfid, root_dfid, agent_id, reason, context_json,
                     proposal_json, impact, status)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, 'PENDING')
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
        self._conn.commit()

    def resolve_request(
        self,
        dfid: str,
        resolved_at: str,
        decision: str,
        proposal_json: Optional[str],
    ) -> None:
        status = _human_decision_to_escalation_status(decision)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE escalation_requests
                SET status = %s,
                    resolved_at = %s::timestamptz,
                    human_decision = %s,
                    proposal_json = COALESCE(%s::jsonb, proposal_json)
                WHERE dfid = %s AND status = 'PENDING'
                """,
                (status, resolved_at, decision, proposal_json, dfid),
            )
        self._conn.commit()

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT dfid, agent_id, reason, context_json::text,
                       proposal_json::text, impact
                FROM escalation_requests
                WHERE status = 'PENDING'
                """
            )
            rows = cur.fetchall()
        return [
            {
                "dfid": r[0],
                "agent_id": r[1],
                "reason": r[2],
                "context": json.loads(r[3] or "{}"),
                "proposal": json.loads(r[4] or "{}"),
                "impact": r[5],
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
        self,
        dfid: str,
        from_status: str,
        to_status: str,
        *,
        root_dfid: Optional[str] = None,
    ) -> None:
        rd = root_dfid or dfid
        with self._conn.cursor() as cur:
            _ensure_root_decision_flow(cur, dfid, _DIR_KERNEL_AGENT)
            cur.execute(
                """
                INSERT INTO flow_transitions
                    (dfid, root_dfid, from_status, to_status)
                VALUES (%s, %s, %s, %s)
                """,
                (dfid, rd, from_status, to_status),
            )
        self._conn.commit()
