"""Regression tests for samples/shared/storage/pg_repo.py and pg_schema.sql."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PG_SCHEMA = _REPO_ROOT / "samples" / "shared" / "storage" / "pg_schema.sql"
_PG_REPO = _REPO_ROOT / "samples" / "shared" / "storage" / "pg_repo.py"

_DDL_STMT_RE = re.compile(
    r"CREATE (?:TABLE|INDEX) IF NOT EXISTS\s+[\s\S]+?;\s*",
    re.IGNORECASE,
)

_CANONICAL_TABLES = frozenset(
    {
        "agent_registry",
        "decision_flows",
        "flow_context",
        "agent_state",
        "decision_feedback_trajectory",
        "idempotency_cache",
        "saga_dirty_state",
        "resource_locks",
        "intent_retry",
        "escalation_budget",
        "escalation_requests",
        "flow_transitions",
        "decision_ledger_entries",
        "decision_audit_events",
    }
)


def _ddl_statements() -> list[str]:
    sql = _PG_SCHEMA.read_text(encoding="utf-8")
    return [m.group(0).strip() for m in _DDL_STMT_RE.finditer(sql)]


def test_pg_schema_ddl_parses_fourteen_tables_and_twenty_eight_indexes() -> None:
    stmts = _ddl_statements()
    tables = [s for s in stmts if s.upper().startswith("CREATE TABLE")]
    indexes = [s for s in stmts if s.upper().startswith("CREATE INDEX")]
    assert len(stmts) == 42
    assert len(tables) == 14
    assert len(indexes) == 28


def test_pg_schema_table_names_match_canonical_model() -> None:
    stmts = _ddl_statements()
    found: set[str] = set()
    for stmt in stmts:
        if not stmt.upper().startswith("CREATE TABLE"):
            continue
        m = re.search(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", stmt, re.I)
        assert m is not None
        found.add(m.group(1))
    assert found == _CANONICAL_TABLES


def test_pg_repo_has_no_legacy_table_references() -> None:
    text = _PG_REPO.read_text(encoding="utf-8")
    for legacy in (
        "context_session",
        "context_state",
        "WHERE key =",
        "'RESOLVED'",
    ):
        assert legacy not in text


@pytest.fixture(scope="module")
def pg_repo_module():
    pytest.importorskip("psycopg2")
    import sys

    shared = _REPO_ROOT / "samples" / "shared"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    from storage import pg_repo

    return pg_repo


def test_human_decision_to_escalation_status(pg_repo_module) -> None:
    fn = pg_repo_module._human_decision_to_escalation_status
    assert fn("ABORT") == "REJECTED"
    assert fn("approve") == "APPROVED"


def test_request_hash_is_stable(pg_repo_module) -> None:
    fn = pg_repo_module._request_hash
    payload = {"dfid": "df-1", "ok": True}
    assert fn(payload) == fn(payload)
    assert fn({"a": 1}) != fn({"a": 2})


def test_pg_integration_smoke(pg_repo_module) -> None:
    """Optional live PostgreSQL smoke (set DIR_PG_TEST_DSN=postgresql://...)."""
    import os

    dsn = os.environ.get("DIR_PG_TEST_DSN")
    if not dsn:
        pytest.skip("DIR_PG_TEST_DSN not set")

    psycopg2 = pytest.importorskip("psycopg2")
    apply_schema = pg_repo_module.apply_schema
    build_repository = pg_repo_module.build_repository

    conn = psycopg2.connect(dsn)
    try:
        apply_schema(conn)
        repo = build_repository(conn)
        repo.context.set_session("df-pg-smoke", '{"ok":true}', agent_id="agent-smoke")
        assert repo.context.get_session("df-pg-smoke") == '{"ok":true}'
        repo.decision_audit.record(
            "df-pg-smoke",
            "SMOKE",
            agent_id="agent-smoke",
            details={"source": "test_pg_repo"},
        )
        events = repo.decision_audit.events_for_dfid("df-pg-smoke")
        assert events[-1]["event_type"] == "SMOKE"

        from dir_core.models import ProofCarryingIntent

        pci = ProofCarryingIntent(
            dfid="df-pg-smoke",
            intent_payload={"action": "BIND"},
            context_ref="ctx-hash",
            evidence_hash="ev-hash",
            signature="sig",
        )
        repo.decision_ledger.append(pci, agent_id="agent-smoke")
        stored = repo.decision_ledger.get_by_dfid("df-pg-smoke")
        assert stored is not None
        assert stored["evidence_hash"] == "ev-hash"
    finally:
        conn.rollback()
        conn.close()
