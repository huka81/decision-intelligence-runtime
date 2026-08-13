"""Tests for governance context pack loading and compilation."""

from __future__ import annotations

from tools.contract.governance.context import (
    build_governance_context,
    compile_authoring_rules_for_prompt,
    compile_context_for_prompt,
)
from tools.contract.governance.loader import load_authoring_rules, load_governance_pack, quote_hash, verify_pack_integrity


def test_load_authoring_rules() -> None:
    rules = load_authoring_rules()
    assert "sections" in rules
    assert "constraint_layers" in rules
    assert "transaction_invariant" in rules["constraint_layers"]
    text = compile_authoring_rules_for_prompt()
    assert "Hard authoring rules" in text


def test_load_governance_pack_integrity() -> None:
    pack = load_governance_pack("roa-dir-v1")
    assert pack.pack_id == "roa-dir-v1"
    errors = verify_pack_integrity(pack)
    assert errors == []


def test_build_governance_context_fundamentals() -> None:
    ctx = build_governance_context(preset="trading", role="EXECUTOR")
    assert ctx["pack_id"] == "roa-dir-v1"
    assert "DIR-BOOTSTRAP-001" in ctx["clause_ids"]
    assert ctx["context_hash"]


def test_compile_context_for_prompt_includes_clauses() -> None:
    ctx = build_governance_context(preset="fraud_gate", role="EXECUTOR")
    text = compile_context_for_prompt(ctx)
    assert "DIR-BOOTSTRAP-001" in text
    assert "Contract authoring ontology" in text
    assert "transaction_invariant" in text
    assert "aggregate_policy" in text
    assert "1t" in text
    assert "Mission does NOT grant execution authority" in text


def test_quote_hash_stable() -> None:
    q = "ROA agents think."
    assert quote_hash(q) == quote_hash(q)
