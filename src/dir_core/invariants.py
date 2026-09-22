"""Evaluate declarative invariant IR in DIM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .data_types import DimReasonCode
from .models import InvariantSpec, PolicyProposal, RuntimeContractProjection


@dataclass(frozen=True)
class InvariantEvaluationFailure:
    """Structured invariant rejection for DIM and audit."""

    reason: str | DimReasonCode
    invariant_id: str


def get_nested_value(obj: Any, path: str) -> Any:
    """Resolve dot-notation path against a mapping or object."""
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
            continue
        current = getattr(current, part, None)
    return current


def evaluate_range_rule(
    rule: InvariantSpec,
    proposal: PolicyProposal,
) -> Optional[InvariantEvaluationFailure]:
    value = get_nested_value(proposal, rule.field)
    if value is None:
        return InvariantEvaluationFailure(
            reason=DimReasonCode.CONTRACT_PARAMETER_MISSING,
            invariant_id=rule.id,
        )
    try:
        actual = float(value)
    except (TypeError, ValueError):
        return InvariantEvaluationFailure(
            reason=f"Invalid numeric field for invariant {rule.id}",
            invariant_id=rule.id,
        )
    if rule.min is not None and actual < float(rule.min):
        return InvariantEvaluationFailure(
            reason=rule.reason_code,
            invariant_id=rule.id,
        )
    if rule.max is not None and actual > float(rule.max):
        return InvariantEvaluationFailure(
            reason=rule.reason_code,
            invariant_id=rule.id,
        )
    return None


def evaluate_set_rule(
    rule: InvariantSpec,
    proposal: PolicyProposal,
) -> Optional[InvariantEvaluationFailure]:
    value = get_nested_value(proposal, rule.field)
    if value is None:
        return InvariantEvaluationFailure(
            reason=DimReasonCode.CONTRACT_PARAMETER_MISSING,
            invariant_id=rule.id,
        )

    denied_match = False
    if rule.denied:
        if rule.match == "substring" and isinstance(value, str):
            normalized = value.casefold()
            denied_match = any(
                isinstance(candidate, str)
                and candidate.casefold() in normalized
                for candidate in rule.denied
            )
        elif isinstance(value, str):
            denied_match = any(
                isinstance(candidate, str)
                and candidate.casefold() == value.casefold()
                for candidate in rule.denied
            )
        else:
            denied_match = value in rule.denied
    if denied_match:
        return InvariantEvaluationFailure(
            reason=rule.reason_code,
            invariant_id=rule.id,
        )

    if rule.allowed and value not in rule.allowed:
        return InvariantEvaluationFailure(
            reason=rule.reason_code,
            invariant_id=rule.id,
        )
    return None


def evaluate_state_match_rule(
    rule: InvariantSpec,
    proposal: PolicyProposal,
    context: dict[str, Any],
) -> Optional[InvariantEvaluationFailure]:
    if not rule.snapshot_path:
        return InvariantEvaluationFailure(
            reason=f"Invalid state_match invariant {rule.id}: missing snapshot_path",
            invariant_id=rule.id,
        )

    proposed = get_nested_value(proposal, rule.field)
    if proposed is None:
        return InvariantEvaluationFailure(
            reason=DimReasonCode.CONTRACT_PARAMETER_MISSING,
            invariant_id=rule.id,
        )

    snapshot_root = context.get("state", context)
    live = get_nested_value(snapshot_root, rule.snapshot_path.removeprefix("state."))

    if rule.expected is not None and rule.drift_envelope_pct in (None, 0, 0.0):
        if proposed != rule.expected or live != rule.expected:
            return InvariantEvaluationFailure(
                reason=rule.reason_code,
                invariant_id=rule.id,
            )
        return None

    try:
        proposed_num = float(proposed)
        live_num = float(live) if live is not None else None
    except (TypeError, ValueError):
        if proposed != live:
            return InvariantEvaluationFailure(
                reason=rule.reason_code,
                invariant_id=rule.id,
            )
        return None

    if live_num is None:
        return InvariantEvaluationFailure(
            reason=DimReasonCode.CONTRACT_PARAMETER_MISSING,
            invariant_id=rule.id,
        )

    envelope = float(rule.drift_envelope_pct or 0.0)
    if envelope <= 0:
        if proposed_num != live_num:
            return InvariantEvaluationFailure(
                reason=rule.reason_code,
                invariant_id=rule.id,
            )
        return None

    if live_num == 0:
        delta_pct = abs(proposed_num - live_num)
    else:
        delta_pct = abs(proposed_num - live_num) / abs(live_num) * 100.0

    if delta_pct > envelope:
        return InvariantEvaluationFailure(
            reason=rule.reason_code,
            invariant_id=rule.id,
        )
    return None


def evaluate_invariants(
    proposal: PolicyProposal,
    projection: RuntimeContractProjection,
    context: dict[str, Any],
) -> list[InvariantEvaluationFailure]:
    """Evaluate all active invariants on the projection; return every failure."""
    failures: list[InvariantEvaluationFailure] = []
    for rule in projection.invariants:
        if (
            rule.applies_to_policy_kinds
            and proposal.policy_kind not in rule.applies_to_policy_kinds
        ):
            continue
        if rule.type == "range":
            failure = evaluate_range_rule(rule, proposal)
        elif rule.type == "set":
            failure = evaluate_set_rule(rule, proposal)
        elif rule.type == "state_match":
            failure = evaluate_state_match_rule(rule, proposal, context)
        else:
            failures.append(
                InvariantEvaluationFailure(
                    reason=f"Unsupported invariant type: {rule.type}",
                    invariant_id=rule.id,
                )
            )
            continue
        if failure is not None:
            failures.append(failure)
    return failures
