"""Tests for dir.pci module."""

from dir_core.models import ProofCarryingIntent
from dir_core.pci import (
    ProofChecker,
    compute_evidence_hash,
    hash_content,
    proposal_params_for_hash,
)


def test_hash_content() -> None:
    h = hash_content({"a": 1, "b": 2})
    assert len(h) == 64
    assert h == hash_content({"b": 2, "a": 1})  # canonical order


def test_compute_evidence_hash() -> None:
    h = compute_evidence_hash("dfid1", "ctx1", "contract1", '{"x":1}')
    assert len(h) == 64
    h2 = compute_evidence_hash("dfid1", "ctx1", "contract1", '{"x":1}')
    assert h == h2
    h3 = compute_evidence_hash("dfid2", "ctx1", "contract1", '{"x":1}')
    assert h != h3


def test_proposal_params_for_hash() -> None:
    s = proposal_params_for_hash({"coverage_limit": 100, "industry": "Retail"})
    assert "coverage_limit" in s
    assert "Retail" in s


def test_proof_checker_verify_ok() -> None:
    ctx_hash = hash_content({"x": 1})
    contract_hash = hash_content({"max": 100})
    params = proposal_params_for_hash({"a": 1})
    evidence = compute_evidence_hash("df1", ctx_hash, contract_hash, params)
    pci = ProofCarryingIntent(
        dfid="df1",
        intent_payload={"a": 1},
        context_ref=ctx_hash,
        evidence_hash=evidence,
        signature="",
    )
    store = type("Store", (), {"_h": ctx_hash})()
    store.get_context_hash = lambda: store._h
    registry = type("Reg", (), {"_h": contract_hash})()
    registry.get_contract_hash = lambda: registry._h

    ok, reason = ProofChecker().verify(
        pci,
        get_context_hash=store.get_context_hash,
        get_contract_hash=registry.get_contract_hash,
        get_proposal_params=lambda i: proposal_params_for_hash(i),
    )
    assert ok is True
    assert reason == "OK"


def test_proof_checker_verify_mismatch() -> None:
    pci = ProofCarryingIntent(
        dfid="df1",
        intent_payload={"a": 1},
        context_ref="abc",
        evidence_hash="0" * 64,
        signature="",
    )
    ok, reason = ProofChecker().verify(
        pci,
        get_context_hash=lambda: "abc",
        get_contract_hash=lambda: "def",
        get_proposal_params=lambda i: "xyz",
    )
    assert ok is False
    assert "Evidence Invalid" in reason

