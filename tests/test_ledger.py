"""Tests for dir.ledger module."""

from dir_core.ledger import DecisionLedger
from dir_core.models import ProofCarryingIntent
from dir_core.storage import MemoryDecisionLedgerStorage


def test_ledger_append_and_entries() -> None:
    ledger = DecisionLedger()
    pci = ProofCarryingIntent(
        dfid="df1",
        intent_payload={"x": 1},
        context_ref="ctx1",
        evidence_hash="abc",
        signature="sig1",
    )
    ledger.append(pci, agent_id="agent1")
    entries = ledger.entries()
    assert len(entries) == 1
    assert entries[0]["dfid"] == "df1"
    assert entries[0]["intent_payload"] == {"x": 1}
    assert entries[0]["context_ref"] == "ctx1"
    assert entries[0]["evidence_hash"] == "abc"
    assert entries[0]["signature"] == "sig1"


def test_ledger_len() -> None:
    ledger = DecisionLedger()
    assert len(ledger) == 0
    ledger.append(
        ProofCarryingIntent(
            dfid="d1",
            intent_payload={},
            context_ref="",
            evidence_hash="",
        ),
        agent_id="agent1",
    )
    assert len(ledger) == 1


def test_ledger_entries_copy() -> None:
    ledger = DecisionLedger()
    ledger.append(
        ProofCarryingIntent(
            dfid="d1",
            intent_payload={"a": 1},
            context_ref="ctx",
            evidence_hash="hash",
        ),
        agent_id="agent1",
    )
    e1 = ledger.entries()
    e2 = ledger.entries()
    assert e1 is not e2
    assert e1 == e2


def test_ledger_backed_by_memory_storage() -> None:
    storage = MemoryDecisionLedgerStorage()
    ledger = DecisionLedger(storage=storage)
    pci = ProofCarryingIntent(
        dfid="df-storage",
        intent_payload={"premium": 100},
        context_ref="ctx-ref",
        evidence_hash="ev-hash",
        signature="sig",
    )
    ledger.append(pci, agent_id="underwriter")
    assert len(ledger) == 1
    assert storage.get_by_dfid("df-storage") is not None
    assert storage.get_by_dfid("df-storage")["agent_id"] == "underwriter"
