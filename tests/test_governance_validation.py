"""Tests for governance analysis validation."""

from __future__ import annotations

from tools.contract.governance.models import (
    ActionClass,
    GovernanceAnalysis,
    GoalModel,
    InvariantCandidate,
    PredicateAST,
    SourceBinding,
)
from tools.contract.governance.validation import validate_governance_analysis


def _valid_analysis() -> GovernanceAnalysis:
    return GovernanceAnalysis(
        goal=GoalModel(
            objective="Execute trades within limits",
            source_bindings=[SourceBinding(clause_id="DIR-BOOTSTRAP-001", rationale="Bootstrap")],
        ),
        action_classes=[
            ActionClass(
                action_type="BUY",
                reversibility="irreversible",
                linked_limit_key="max_order_size_usd",
                source_bindings=[SourceBinding(clause_id="DIR-BOOTSTRAP-001")],
            ),
        ],
        invariant_candidates=[
            InvariantCandidate(
                invariant_id="INV-ORDER",
                constraint_class="transaction_invariant",
                applies_to_actions=["BUY"],
                predicate=PredicateAST(op="le", variable="order_value", value=50000.0),
                enforcement_target="DIM",
                linked_limit_key="max_order_size_usd",
                source_bindings=[SourceBinding(clause_id="DIR-BOOTSTRAP-001")],
            ),
        ],
    )


def test_semantic_warnings_do_not_block() -> None:
    analysis = GovernanceAnalysis(
        goal=GoalModel(objective="Trade safely"),
        action_classes=[],
        invariant_candidates=[],
        ambiguities=["What is the exact drawdown tolerance?"],
    )
    contract = {
        "metadata": {"contract_id": "bot", "version": "1.0.0", "owner": "o@example.com"},
        "subject": {"agent_id": "bot", "role": "EXECUTOR"},
        "mission": {"statement": "Trade"},
        "authority": {
            "allowed_policy_types": ["BUY"],
            "limits": {"max_order_size_usd": {"value": 1000.0, "unit": "USD"}},
        },
    }
    report = validate_governance_analysis(
        analysis=analysis,
        contract_dict=contract,
        preset="trading",
    )
    assert report.blocking_ok
    assert report.has_warnings


def test_invalid_clause_ref_blocks() -> None:
    analysis = GovernanceAnalysis(
        invariant_candidates=[
            InvariantCandidate(
                invariant_id="INV-BAD",
                constraint_class="transaction_invariant",
                source_bindings=[SourceBinding(clause_id="NONEXISTENT-CLAUSE")],
            ),
        ],
    )
    report = validate_governance_analysis(
        analysis=analysis,
        contract_dict={
            "subject": {"agent_id": "bot", "role": "EXECUTOR"},
            "mission": {"statement": "m"},
            "authority": {"limits": {}},
        },
    )
    assert not report.blocking_ok
    assert any(i.code == "INVALID_CLAUSE_REF" for i in report.blocking_errors)


def test_sat_unsat_blocks() -> None:
    analysis = GovernanceAnalysis(
        invariant_candidates=[
            InvariantCandidate(
                invariant_id="INV-A",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="le", variable="x", value=10.0),
                source_bindings=[SourceBinding(clause_id="DIR-BOOTSTRAP-001")],
            ),
            InvariantCandidate(
                invariant_id="INV-B",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="ge", variable="x", value=20.0),
                source_bindings=[SourceBinding(clause_id="DIR-BOOTSTRAP-001")],
            ),
        ],
    )
    report = validate_governance_analysis(
        analysis=analysis,
        contract_dict={
            "subject": {"agent_id": "bot", "role": "EXECUTOR"},
            "mission": {"statement": "m"},
            "authority": {"limits": {}},
        },
    )
    assert not report.blocking_ok
    assert any(i.code == "SAT_UNSAT" for i in report.blocking_errors)


def test_valid_analysis_passes() -> None:
    analysis = _valid_analysis()
    contract = {
        "metadata": {"contract_id": "bot", "version": "1.0.0", "owner": "o@example.com"},
        "subject": {"agent_id": "bot", "role": "EXECUTOR"},
        "mission": {"statement": "Trade safely"},
        "authority": {
            "allowed_policy_types": ["BUY"],
            "limits": {"max_order_size_usd": {"value": 50000.0, "unit": "USD"}},
        },
    }
    report = validate_governance_analysis(analysis=analysis, contract_dict=contract)
    assert report.blocking_ok
