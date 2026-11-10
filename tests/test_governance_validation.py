"""Tests for governance analysis validation."""

from __future__ import annotations

from tools.contract.governance.models import (
    ActionClass,
    GoalModel,
    GovernanceAnalysis,
    InvariantCandidate,
    PredicateAST,
    SourceBinding,
)
from tools.contract.governance.validation import validate_governance_analysis
from tools.contract.schema import IRREVERSIBLE_LIMIT_KEYS


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


def test_candidate_ast_unsat_is_advisory() -> None:
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
    assert report.blocking_ok
    assert any(i.code == "GOVERNANCE_AST_UNSAT" for i in report.warnings)
    check = report.formal_checks["governance_ast"]
    assert check.status == "contradictory"
    assert check.invariant_ids == ["INV-A", "INV-B"]


def test_nested_candidate_ast_is_translated_recursively() -> None:
    analysis = GovernanceAnalysis(
        invariant_candidates=[
            InvariantCandidate(
                invariant_id="INV-NESTED",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(
                    op="and",
                    left=PredicateAST(op="le", variable="x", value=10.0),
                    right=PredicateAST(op="ge", variable="x", value=20.0),
                ),
            ),
        ],
    )
    report = validate_governance_analysis(
        analysis=analysis,
        contract_dict={"authority": {"invariants": []}},
    )
    assert report.blocking_ok
    assert report.formal_checks["governance_ast"].status == "contradictory"


def test_candidate_predicates_for_disjoint_actions_do_not_conflict() -> None:
    from tools.contract.governance.solver import check_governance_ast

    result = check_governance_ast(
        [
            InvariantCandidate(
                invariant_id="INV-BUY",
                constraint_class="transaction_invariant",
                applies_to_actions=["BUY"],
                predicate=PredicateAST(op="le", variable="amount", value=10),
            ),
            InvariantCandidate(
                invariant_id="INV-SELL",
                constraint_class="transaction_invariant",
                applies_to_actions=["SELL"],
                predicate=PredicateAST(op="ge", variable="amount", value=20),
            ),
        ]
    )
    assert result.status == "verified"


def test_candidate_ast_membership_negation_and_disjunction() -> None:
    from tools.contract.governance.solver import check_governance_ast

    satisfiable = check_governance_ast(
        [
            InvariantCandidate(
                invariant_id="INV-OR",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(
                    op="or",
                    left=PredicateAST(op="lt", variable="x", value=0),
                    right=PredicateAST(op="gt", variable="x", value=10),
                ),
            )
        ]
    )
    assert satisfiable.status == "verified"

    contradictory = check_governance_ast(
        [
            InvariantCandidate(
                invariant_id="INV-IN",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="in", variable="x", right=[1, 2]),
            ),
            InvariantCandidate(
                invariant_id="INV-NOT-IN",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="not_in", variable="x", right=[1, 2]),
            ),
            InvariantCandidate(
                invariant_id="INV-NOT",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(
                    op="not",
                    left=PredicateAST(op="eq", variable="enabled", value=True),
                ),
            ),
            InvariantCandidate(
                invariant_id="INV-EQ",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="eq", variable="enabled", value=True),
            ),
        ]
    )
    assert contradictory.status == "contradictory"


def test_candidate_ast_unit_mismatch_is_not_verified() -> None:
    from tools.contract.governance.models import VariableSpec
    from tools.contract.governance.solver import check_governance_ast

    result = check_governance_ast(
        [
            InvariantCandidate(
                invariant_id="INV-UNIT-MISMATCH",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(
                    op="le",
                    left=VariableSpec(name="amount", unit="USD"),
                    right=VariableSpec(name="amount", unit="EUR"),
                ),
            )
        ]
    )
    assert result.status == "not_verified"


def test_compiled_runtime_range_contradiction_blocks() -> None:
    report = validate_governance_analysis(
        analysis=GovernanceAnalysis(),
        contract_dict={
            "authority": {
                "invariants": [
                    {"id": "INV-MIN", "type": "range", "field": "params.value", "min": 20},
                    {"id": "INV-MAX", "type": "range", "field": "params.value", "max": 10},
                ],
            },
        },
    )
    assert not report.blocking_ok
    assert any(issue.code == "RUNTIME_INVARIANTS_UNSAT" for issue in report.blocking_errors)
    assert report.formal_checks["runtime_invariants"].invariant_ids == [
        "INV-MAX",
        "INV-MIN",
    ]


def test_compiled_runtime_set_contradiction_blocks() -> None:
    report = validate_governance_analysis(
        analysis=GovernanceAnalysis(),
        contract_dict={
            "authority": {
                "invariants": [
                    {"id": "INV-ALLOW", "type": "set", "field": "params.count", "allowed": [1]},
                    {"id": "INV-DENY", "type": "set", "field": "params.count", "denied": [1]},
                ],
            },
        },
    )
    assert not report.blocking_ok
    assert report.formal_checks["runtime_invariants"].status == "contradictory"


def test_runtime_invariants_for_disjoint_policy_scopes_do_not_conflict() -> None:
    report = validate_governance_analysis(
        analysis=GovernanceAnalysis(),
        contract_dict={
            "authority": {
                "invariants": [
                    {
                        "id": "INV-BUY-MIN",
                        "type": "range",
                        "field": "params.value",
                        "min": 20,
                        "applies_to_policy_kinds": ["BUY"],
                    },
                    {
                        "id": "INV-SELL-MAX",
                        "type": "range",
                        "field": "params.value",
                        "max": 10,
                        "applies_to_policy_kinds": ["SELL"],
                    },
                ],
            },
        },
    )
    assert report.blocking_ok
    assert report.formal_checks["runtime_invariants"].status == "verified"


def test_state_match_is_reported_as_not_verified() -> None:
    report = validate_governance_analysis(
        analysis=GovernanceAnalysis(),
        contract_dict={
            "authority": {
                "invariants": [
                    {
                        "id": "INV-STATE",
                        "type": "state_match",
                        "field": "params.price",
                        "snapshot_path": "state.price",
                    },
                ],
            },
        },
    )
    assert report.blocking_ok
    assert report.formal_checks["runtime_invariants"].status == "not_verified"
    assert any(
        issue.code == "RUNTIME_INVARIANTS_NOT_VERIFIED"
        for issue in report.warnings
    )


def test_case_insensitive_runtime_string_denial_is_not_claimed_verified() -> None:
    from tools.contract.governance.solver import check_runtime_invariants

    result = check_runtime_invariants(
        {
            "authority": {
                "invariants": [
                    {
                        "id": "INV-COUNTRY",
                        "type": "set",
                        "field": "params.country",
                        "allowed": ["US"],
                        "denied": ["us"],
                    }
                ]
            }
        }
    )
    assert result.status == "not_verified"


def test_solver_unknown_is_not_reported_as_success(monkeypatch) -> None:
    import z3

    from tools.contract.governance import solver

    monkeypatch.setattr(solver, "_solver_status", lambda _solver: z3.unknown)
    result = solver.check_governance_ast(
        [
            InvariantCandidate(
                invariant_id="INV-UNKNOWN",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="le", variable="x", value=10.0),
            )
        ]
    )
    assert result.status == "not_verified"


def test_runtime_solver_unknown_is_not_reported_as_success(monkeypatch) -> None:
    import z3

    from tools.contract.governance import solver

    monkeypatch.setattr(solver, "_solver_status", lambda _solver: z3.unknown)
    result = solver.check_runtime_invariants(
        {
            "authority": {
                "invariants": [
                    {"id": "INV-UNKNOWN", "type": "range", "field": "params.value", "max": 10}
                ]
            }
        }
    )
    assert result.status == "not_verified"


def test_missing_z3_is_not_reported_as_success(monkeypatch) -> None:
    import sys

    from tools.contract.governance.solver import (
        check_governance_ast,
        check_runtime_invariants,
    )

    monkeypatch.setitem(sys.modules, "z3", None)
    result = check_governance_ast(
        [
            InvariantCandidate(
                invariant_id="INV-NO-Z3",
                constraint_class="transaction_invariant",
                predicate=PredicateAST(op="le", variable="x", value=10.0),
            )
        ]
    )
    assert result.status == "not_verified"
    runtime_result = check_runtime_invariants({"authority": {"invariants": []}})
    assert runtime_result.status == "not_verified"


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


def test_noncanonical_linked_limit_is_warning_with_allowed_keys() -> None:
    analysis = _valid_analysis()
    analysis.invariant_candidates[0].linked_limit_key = "max_payout_usd"
    report = validate_governance_analysis(
        analysis=analysis,
        contract_dict={
            "authority": {
                "allowed_policy_types": ["BUY"],
                "limits": {"max_order_size_usd": {"value": 50000.0, "unit": "USD"}},
            },
        },
    )

    assert report.blocking_ok
    issue = next(issue for issue in report.warnings if issue.code == "INVALID_LIMIT_KEY")
    assert issue.severity == "warning"
    assert "max_payout_usd" in issue.message
    for key in IRREVERSIBLE_LIMIT_KEYS:
        assert key in issue.message
