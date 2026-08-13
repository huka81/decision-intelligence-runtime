"""Deterministic and semantic validation for governance analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ..schema import IRREVERSIBLE_LIMIT_KEYS, normalize_contract_dict, PLACEHOLDER_AGENT_IDS, PLACEHOLDER_OWNERS
from .loader import load_governance_pack, verify_pack_integrity
from .models import (
    GovernanceAnalysis,
    GovernanceValidationReport,
    InvariantCandidate,
    PredicateAST,
    ValidationIssue,
)

_SUPPORTED_PREDICATE_OPS = frozenset(
    {"eq", "neq", "lt", "le", "gt", "ge", "in", "not_in", "and", "or", "not"}
)


def validate_governance_analysis(
    *,
    analysis: Optional[GovernanceAnalysis],
    contract_dict: Dict[str, Any],
    pack_id: str = "roa-dir-v1",
    preset: Optional[str] = None,
) -> GovernanceValidationReport:
    """
    Run blocking formal checks and non-blocking semantic warnings.

    Blocking: pack integrity, invalid clause refs, duplicate ids, AST shape,
    unsupported predicate ops when predicate present.
    Warnings: coverage gaps, missing goal, unclassified actions, etc.
    """
    blocking: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    formal_checks: Dict[str, Any] = {"sat": None, "liveness": None}

    try:
        pack = load_governance_pack(pack_id)
        pack_errors = verify_pack_integrity(pack)
        for msg in pack_errors:
            blocking.append(
                ValidationIssue(
                    code="PACK_INTEGRITY",
                    message=msg,
                    severity="blocking",
                )
            )
        valid_clause_ids = {c.clause_id for c in pack.clauses}
    except Exception as exc:
        blocking.append(
            ValidationIssue(
                code="PACK_LOAD",
                message=str(exc),
                severity="blocking",
            )
        )
        valid_clause_ids = set()

    if analysis is None:
        warnings.append(
            ValidationIssue(
                code="ANALYSIS_MISSING",
                message="No governance_analysis from LLM; goal and invariant traceability unavailable.",
                severity="warning",
            )
        )
        return GovernanceValidationReport(
            blocking_errors=blocking,
            warnings=warnings,
            formal_checks=formal_checks,
        )

    _validate_references(analysis, valid_clause_ids, blocking, warnings)
    _validate_invariant_candidates(analysis.invariant_candidates, blocking, warnings)
    _validate_ast_and_sat(analysis.invariant_candidates, blocking, warnings, formal_checks)
    _validate_semantic_coverage(
        analysis, contract_dict, preset, warnings
    )
    _validate_analysis_contract_consistency(
        analysis, contract_dict, blocking, warnings
    )

    return GovernanceValidationReport(
        blocking_errors=blocking,
        warnings=warnings,
        formal_checks=formal_checks,
    )


def _validate_references(
    analysis: GovernanceAnalysis,
    valid_clause_ids: Set[str],
    blocking: List[ValidationIssue],
    warnings: List[ValidationIssue],
) -> None:
    seen_invariant_ids: Set[str] = set()
    for inv in analysis.invariant_candidates:
        if inv.invariant_id in seen_invariant_ids:
            blocking.append(
                ValidationIssue(
                    code="DUPLICATE_INVARIANT_ID",
                    message=f"Duplicate invariant_id: {inv.invariant_id}",
                    severity="blocking",
                    field="invariant_candidates",
                )
            )
        seen_invariant_ids.add(inv.invariant_id)
        for binding in inv.source_bindings:
            if valid_clause_ids and binding.clause_id not in valid_clause_ids:
                blocking.append(
                    ValidationIssue(
                        code="INVALID_CLAUSE_REF",
                        message=f"Unknown clause_id in source_bindings: {binding.clause_id}",
                        severity="blocking",
                        field="source_bindings",
                    )
                )

    if analysis.goal:
        for binding in analysis.goal.source_bindings:
            if valid_clause_ids and binding.clause_id not in valid_clause_ids:
                blocking.append(
                    ValidationIssue(
                        code="INVALID_CLAUSE_REF",
                        message=f"Unknown clause_id on goal: {binding.clause_id}",
                        severity="blocking",
                        field="goal.source_bindings",
                    )
                )

    for action in analysis.action_classes:
        for binding in action.source_bindings:
            if valid_clause_ids and binding.clause_id not in valid_clause_ids:
                blocking.append(
                    ValidationIssue(
                        code="INVALID_CLAUSE_REF",
                        message=f"Unknown clause_id on action {action.action_type}: {binding.clause_id}",
                        severity="blocking",
                        field="action_classes.source_bindings",
                    )
                )


def _validate_invariant_candidates(
    candidates: List[InvariantCandidate],
    blocking: List[ValidationIssue],
    warnings: List[ValidationIssue],
) -> None:
    for inv in candidates:
        if inv.linked_limit_key and inv.linked_limit_key not in IRREVERSIBLE_LIMIT_KEYS:
            blocking.append(
                ValidationIssue(
                    code="INVALID_LIMIT_KEY",
                    message=f"linked_limit_key '{inv.linked_limit_key}' is not canonical",
                    severity="blocking",
                    field="linked_limit_key",
                )
            )
        if inv.predicate is None and inv.constraint_class == "transaction_invariant":
            warnings.append(
                ValidationIssue(
                    code="INVARIANT_NO_PREDICATE",
                    message=f"Transaction invariant {inv.invariant_id} has no formal predicate.",
                    severity="warning",
                    field="predicate",
                )
            )


def _validate_ast_node(
    node: Optional[PredicateAST],
    path: str,
    blocking: List[ValidationIssue],
) -> None:
    if node is None:
        return
    if node.op not in _SUPPORTED_PREDICATE_OPS:
        blocking.append(
            ValidationIssue(
                code="AST_INVALID_OP",
                message=f"Unsupported predicate op '{node.op}' at {path}",
                severity="blocking",
                field=path,
            )
        )
    if node.op in ("and", "or"):
        if not isinstance(node.left, PredicateAST) or not isinstance(node.right, PredicateAST):
            blocking.append(
                ValidationIssue(
                    code="AST_SHAPE",
                    message=f"Binary op {node.op} requires PredicateAST children at {path}",
                    severity="blocking",
                    field=path,
                )
            )
        else:
            _validate_ast_node(node.left, f"{path}.left", blocking)
            _validate_ast_node(node.right, f"{path}.right", blocking)
    elif node.op == "not":
        if not isinstance(node.left, PredicateAST):
            blocking.append(
                ValidationIssue(
                    code="AST_SHAPE",
                    message=f"not requires PredicateAST child at {path}",
                    severity="blocking",
                    field=path,
                )
            )
        else:
            _validate_ast_node(node.left, f"{path}.left", blocking)


def _validate_ast_and_sat(
    candidates: List[InvariantCandidate],
    blocking: List[ValidationIssue],
    warnings: List[ValidationIssue],
    formal_checks: Dict[str, Any],
) -> None:
    numeric_bounds: List[tuple[str, str, float]] = []
    for inv in candidates:
        if inv.predicate is not None:
            _validate_ast_node(inv.predicate, inv.invariant_id, blocking)
            _collect_numeric_bounds(inv, numeric_bounds)

    if not numeric_bounds:
        formal_checks["sat"] = {"ok": True, "detail": "no formal numeric predicates"}
        formal_checks["liveness"] = {"ok": True, "detail": "no constraints to check"}
        return

    try:
        from z3 import And, Real, Solver, sat

        solver = Solver()
        variables: Dict[str, Any] = {}
        for var_name, _, _ in numeric_bounds:
            if var_name not in variables:
                variables[var_name] = Real(var_name)
        constraints = []
        for var_name, op, bound in numeric_bounds:
            v = variables[var_name]
            if op == "le":
                constraints.append(v <= bound)
            elif op == "lt":
                constraints.append(v < bound)
            elif op == "ge":
                constraints.append(v >= bound)
            elif op == "gt":
                constraints.append(v > bound)
            elif op == "eq":
                constraints.append(v == bound)
        if constraints:
            solver.add(And(*constraints))
            sat_result = solver.check()
            formal_checks["sat"] = {
                "ok": sat_result == sat,
                "detail": str(sat_result),
            }
            if sat_result != sat:
                blocking.append(
                    ValidationIssue(
                        code="SAT_UNSAT",
                        message="Invariant numeric bounds are mutually unsatisfiable.",
                        severity="blocking",
                    )
                )
            witness = Solver()
            for c in constraints:
                witness.add(c)
            witness.add(variables[list(variables.keys())[0]] >= 0)
            liveness = witness.check()
            formal_checks["liveness"] = {
                "ok": liveness == sat,
                "detail": str(liveness),
            }
            if liveness != sat:
                warnings.append(
                    ValidationIssue(
                        code="LIVENESS_GAP",
                        message="No witness found for permitted numeric region (may be over-constrained).",
                        severity="warning",
                    )
                )
    except ImportError:
        formal_checks["sat"] = {
            "ok": None,
            "detail": "z3-solver not installed; skipped SAT check",
        }
        warnings.append(
            ValidationIssue(
                code="SAT_SKIPPED",
                message="z3-solver not available; formal satisfiability not verified.",
                severity="warning",
            )
        )


def _collect_numeric_bounds(
    inv: InvariantCandidate,
    bounds: List[tuple[str, str, float]],
) -> None:
    if inv.predicate is None:
        return
    node = inv.predicate
    if node.variable and node.op in ("le", "lt", "ge", "gt", "eq") and node.value is not None:
        if isinstance(node.value, (int, float)):
            bounds.append((node.variable, node.op, float(node.value)))


def _validate_semantic_coverage(
    analysis: GovernanceAnalysis,
    contract_dict: Dict[str, Any],
    preset: Optional[str],
    warnings: List[ValidationIssue],
) -> None:
    normalized = normalize_contract_dict(contract_dict)
    role = normalized.get("subject", {}).get("role", "EXECUTOR")
    allowed = set(
        normalized.get("authority", {}).get("allowed_policy_types") or []
    )
    limits = normalized.get("authority", {}).get("limits") or {}

    if not analysis.goal or not analysis.goal.objective.strip():
        warnings.append(
            ValidationIssue(
                code="GOAL_MISSING",
                message="Goal objective is empty; mission traceability is weak.",
                severity="warning",
            )
        )

    classified = {a.action_type for a in analysis.action_classes}
    for action in allowed:
        if action not in classified:
            warnings.append(
                ValidationIssue(
                    code="ACTION_UNCLASSIFIED",
                    message=f"Allowed action '{action}' has no reversibility classification.",
                    severity="warning",
                )
            )

    irreversible_actions = [
        a for a in analysis.action_classes if a.reversibility == "irreversible"
    ]
    for action in irreversible_actions:
        if not action.linked_limit_key and action.action_type in allowed:
            has_limit = any(
                inv.linked_limit_key for inv in analysis.invariant_candidates
            ) or bool(limits)
            if not has_limit:
                warnings.append(
                    ValidationIssue(
                        code="IRREVERSIBLE_NO_LIMIT",
                        message=f"Irreversible action '{action.action_type}' lacks linked limit.",
                        severity="warning",
                    )
                )

    if role == "INTERFACE" and allowed:
        warnings.append(
            ValidationIssue(
                code="INTERFACE_AUTHORITY",
                message="INTERFACE role should not declare allowed_policy_types.",
                severity="warning",
            )
        )

    if analysis.ambiguities:
        for amb in analysis.ambiguities[:5]:
            warnings.append(
                ValidationIssue(
                    code="OPEN_AMBIGUITY",
                    message=f"Unresolved ambiguity: {amb}",
                    severity="warning",
                )
            )

    if preset and analysis.goal and not analysis.goal.source_bindings:
        warnings.append(
            ValidationIssue(
                code="GOAL_NO_SOURCE",
                message="Goal has no source_bindings to governance clauses.",
                severity="warning",
            )
        )


def validate_authoring_contract(contract) -> List[str]:
    """
    Blocking authoring rules on a validated CanonicalContract.

    Returns human-readable error strings.
    """
    from ..schema import CanonicalContract

    if not isinstance(contract, CanonicalContract):
        contract = CanonicalContract.model_validate(contract)

    errors: List[str] = []
    agent_id = contract.agent_id.strip()
    contract_id = contract.metadata.contract_id.strip()
    owner = contract.owner.strip()

    if agent_id in PLACEHOLDER_AGENT_IDS or contract_id in PLACEHOLDER_AGENT_IDS:
        errors.append(
            "PLACEHOLDER_IDENTITY: agent_id and contract_id must not be draft_agent"
        )
    if not owner or owner in PLACEHOLDER_OWNERS:
        errors.append(
            "PLACEHOLDER_IDENTITY: owner must be a real human accountability email"
        )

    limits = contract.authority.numeric_limits()
    confidence_below = contract.responsibility.escalation.confidence_below

    for policy in contract.governance.aggregate_policies:
        pid_upper = policy.policy_id.upper()
        if pid_upper.startswith("INV-") or "INVARIANT" in pid_upper:
            errors.append(
                f"INVARIANT_LEAKED_TO_AGGREGATE: policy_id {policy.policy_id} "
                "must not encode transaction invariants; use invariant_candidates"
            )

        metric_lower = policy.metric.lower()
        if "confidence" in metric_lower and abs(policy.threshold - confidence_below) < 1e-9:
            errors.append(
                "ESCALATION_LEAKED_TO_AGGREGATE: confidence threshold belongs in "
                "responsibility.escalation, not aggregate_policies"
            )

        for key, val in limits.items():
            if abs(policy.threshold - val) > 1e-9:
                continue
            if _aggregate_duplicates_limit_key(key, policy.metric, policy.policy_id):
                errors.append(
                    f"AGGREGATE_DUP_LIMIT: {policy.policy_id} duplicates "
                    f"authority.limits.{key} (single-transaction limit)"
                )

    return errors


def _aggregate_duplicates_limit_key(limit_key: str, metric: str, policy_id: str) -> bool:
    key_lower = limit_key.lower()
    metric_lower = metric.lower()
    pid_lower = policy_id.lower()
    if key_lower in metric_lower or key_lower in pid_lower:
        return True
    key_stem = key_lower.replace("_usd", "").replace("_pct", "")
    metric_stem = metric_lower.replace("_usd", "").replace("_pct", "")
    if key_stem and key_stem in metric_stem:
        return True
    for token in (
        "transaction",
        "order",
        "premium",
        "refund",
        "discount",
        "drawdown",
        "confidence",
    ):
        if token in key_lower and token in metric_lower:
            return True
    return False


def _validate_analysis_contract_consistency(
    analysis: GovernanceAnalysis,
    contract_dict: Dict[str, Any],
    blocking: List[ValidationIssue],
    warnings: List[ValidationIssue],
) -> None:
    normalized = normalize_contract_dict(contract_dict)
    limits = normalized.get("authority", {}).get("limits") or {}
    limit_values: Dict[str, float] = {}
    for key, spec in limits.items():
        if isinstance(spec, dict) and "value" in spec:
            limit_values[key] = float(spec["value"])
        elif isinstance(spec, (int, float)):
            limit_values[key] = float(spec)

    aggregate_policies = normalized.get("governance", {}).get("aggregate_policies") or []
    aggregate_ids = {
        p.get("policy_id", "")
        for p in aggregate_policies
        if isinstance(p, dict)
    }

    for inv in analysis.invariant_candidates:
        if inv.constraint_class == "aggregate_policy":
            if inv.invariant_id not in aggregate_ids:
                warnings.append(
                    ValidationIssue(
                        code="AGGREGATE_MISSING_YAML",
                        message=(
                            f"Aggregate invariant candidate {inv.invariant_id} "
                            "has no matching governance.aggregate_policies entry"
                        ),
                        severity="warning",
                    )
                )
            continue

        if inv.constraint_class != "transaction_invariant":
            continue

        linked = inv.linked_limit_key
        if not linked or linked not in limit_values:
            continue
        limit_val = limit_values[linked]
        for policy in aggregate_policies:
            if not isinstance(policy, dict):
                continue
            threshold = policy.get("threshold")
            if threshold is None:
                continue
            if abs(float(threshold) - limit_val) > 1e-9:
                continue
            metric = str(policy.get("metric", "")).lower()
            pid = str(policy.get("policy_id", "")).lower()
            if (
                linked.lower() in metric
                or linked.lower() in pid
                or inv.invariant_id.lower() in pid
            ):
                blocking.append(
                    ValidationIssue(
                        code="INVARIANT_LEAKED_TO_AGGREGATE",
                        message=(
                            f"Invariant {inv.invariant_id} linked to {linked} "
                            f"was copied into aggregate policy {policy.get('policy_id')}"
                        ),
                        severity="blocking",
                    )
                )
