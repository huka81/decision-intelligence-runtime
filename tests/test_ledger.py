"""Tests for dir.ledger module."""

from dir_core.ledger import DecisionLedger
from dir_core.models import ProofCarryingIntent


def test_ledger_append_and_entries() -> None:
    ledger = DecisionLedger()
    pci = ProofCarryingIntent(
        dfid="df1",
        intent_payload={"x": 1},
        context_ref="ctx1",
        evidence_hash="abc",
        signature="",
    )
    ledger.append(pci)
    entries = ledger.entries()
    assert len(entries) == 1
    assert entries[0]["dfid"] == "df1"
    assert entries[0]["intent_payload"] == {"x": 1}
    assert entries[0]["evidence_hash"] == "abc"


def test_ledger_len() -> None:
    ledger = DecisionLedger()
    assert len(ledger) == 0
    ledger.append(
        ProofCarryingIntent(
            dfid="d1",
            intent_payload={},
            context_ref="",
            evidence_hash="",
        )
    )
    assert len(ledger) == 1


def test_ledger_entries_copy() -> None:
    ledger = DecisionLedger()
    ledger.append(
        ProofCarryingIntent(
            dfid="d1",
            intent_payload={"a": 1},
            context_ref="",
            evidence_hash="",
        )
    )
    e1 = ledger.entries()
    e2 = ledger.entries()
    assert e1 is not e2
    assert e1 == e2

