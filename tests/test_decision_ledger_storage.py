"""Tests for DecisionLedger SQLite storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dir_core.models import ProofCarryingIntent
from dir_core.storage.sqlite import SqliteDecisionLedgerStorage


@pytest.fixture
def ledger_db(tmp_path: Path) -> SqliteDecisionLedgerStorage:
    db_path = str(tmp_path / "ledger_test.db")
    return SqliteDecisionLedgerStorage(db_path)


def test_sqlite_append_and_read(ledger_db: SqliteDecisionLedgerStorage) -> None:
    pci = ProofCarryingIntent(
        dfid="df-ledger-1",
        intent_payload={"total_insured_value": 1_000_000, "premium": 5000},
        context_ref="ctx-hash-abc",
        evidence_hash="evidence-hash-xyz",
        signature="roa-sig",
    )
    ledger_db.append(pci, agent_id="underwriter_agent")
    entry = ledger_db.get_by_dfid("df-ledger-1")
    assert entry is not None
    assert entry["intent_payload"]["premium"] == 5000
    assert entry["context_ref"] == "ctx-hash-abc"
    assert entry["evidence_hash"] == "evidence-hash-xyz"
    assert entry["signature"] == "roa-sig"
    assert entry["agent_id"] == "underwriter_agent"


def test_sqlite_append_is_idempotent(ledger_db: SqliteDecisionLedgerStorage) -> None:
    pci = ProofCarryingIntent(
        dfid="df-idem",
        intent_payload={"x": 1},
        context_ref="ctx",
        evidence_hash="hash",
    )
    ledger_db.append(pci, agent_id="agent1")
    ledger_db.append(pci, agent_id="agent1")
    assert len(ledger_db.all_entries_chronological()) == 1


def test_sqlite_all_entries_chronological(
    ledger_db: SqliteDecisionLedgerStorage,
) -> None:
    for i in range(3):
        ledger_db.append(
            ProofCarryingIntent(
                dfid=f"df-{i}",
                intent_payload={"n": i},
                context_ref=f"ctx-{i}",
                evidence_hash=f"hash-{i}",
            ),
            agent_id="agent1",
        )
    entries = ledger_db.all_entries_chronological()
    assert [e["dfid"] for e in entries] == ["df-0", "df-1", "df-2"]

    conn = sqlite3.connect(ledger_db.db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM decision_ledger_entries"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 3
