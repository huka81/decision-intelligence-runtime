"""
Decision Integrity Module (DIM): schema + RBAC + declarative invariant IR.

DIR §6. Validates PolicyProposal; returns ``ValidationVerdict`` with a reason.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .amendments import projection_with_effective_invariants
from .contract_projection import project_contract, ensure_projection_invariants
from .invariants import InvariantEvaluationFailure, evaluate_invariants
from .models import PolicyProposal, RuntimeContractProjection
from .data_types import DimReasonCode, ValidationResult, ValidationVerdict

if TYPE_CHECKING:
    from .intent_retry import IntentRetryGovernor


def _resolve_valid_until(proposal: PolicyProposal) -> Optional[datetime]:
    """Resolve valid_until from proposal (explicit or from validity_window_sec)."""
    if proposal.valid_until is not None:
        return proposal.valid_until
    window_sec = proposal.execution_constraints.get("validity_window_sec")
    if window_sec is not None:
        return proposal.created_at + timedelta(seconds=float(window_sec))
    return None


def _resolve_projection(
    contract: dict[str, Any] | RuntimeContractProjection,
    *,
    now: Optional[datetime] = None,
) -> RuntimeContractProjection:
    projection = (
        contract
        if isinstance(contract, RuntimeContractProjection)
        else project_contract(contract)
    )
    projection = ensure_projection_invariants(projection)
    if projection.parameter_amendments:
        return projection_with_effective_invariants(projection, now=now)
    return projection


def validate_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]] = None,
    now: Optional[datetime] = None,
    retry_governor: Optional["IntentRetryGovernor"] = None,
    contract: Optional[Dict[str, Any] | RuntimeContractProjection] = None,
    custom_validators: Optional[List[Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]]] = None,
) -> ValidationResult:
    """
    Validate a PolicyProposal against schema, RBAC, TTL, contract IR,
    and custom domain-specific validators.
    """
    now = now or datetime.now(timezone.utc)

    if retry_governor is not None and retry_governor.should_abort(proposal.dfid):
        return ValidationVerdict.REJECT, DimReasonCode.REASONING_EXHAUSTION

    def _reject(reason: str | DimReasonCode) -> ValidationResult:
        if retry_governor is not None:
            retry_governor.record_rejection(proposal.dfid)
        return ValidationVerdict.REJECT, reason

    if not proposal.policy_kind:
        return _reject("Missing policy_kind")
    if not proposal.agent_id:
        return _reject("Missing agent_id")

    valid_until = _resolve_valid_until(proposal)
    if valid_until is not None and now > valid_until:
        return _reject(DimReasonCode.TTL_EXPIRED)

    if allowed_agents is not None:
        if proposal.agent_id not in allowed_agents:
            return _reject(f"Agent '{proposal.agent_id}' not authorized (RBAC)")

    if contract:
        projection = _resolve_projection(contract, now=now)

        if isinstance(contract, RuntimeContractProjection) or isinstance(contract, dict):
            safety_rules: Dict[str, Any] = {}
            if isinstance(contract, dict):
                safety_rules = contract.get("safety_rules", contract.get("permissions", contract))
                if not isinstance(safety_rules, dict):
                    safety_rules = {}
        else:
            safety_rules = {}

        min_conf = safety_rules.get("min_confidence_threshold")
        if min_conf is None:
            min_conf = projection.escalation_policy.get("confidence_below")
        if min_conf is not None and proposal.confidence < float(min_conf):
            return _reject(
                f"Proposal confidence ({proposal.confidence}) is below threshold ({min_conf})"
            )

        failures = evaluate_invariants(proposal, projection, context)
        if failures:
            return _reject_invariant_failures(context, failures, _reject)

    state = context.get("state", {})
    risk_score = state.get("risk_score", 0.0)
    if proposal.policy_kind == "deploy_to_production" and risk_score > 0.8:
        return _reject(f"Risk score {risk_score} too high for deployment")

    if custom_validators:
        contract_payload: Dict[str, Any]
        if isinstance(contract, RuntimeContractProjection):
            contract_payload = contract.model_dump(mode="json")
        elif isinstance(contract, dict):
            contract_payload = contract
        else:
            contract_payload = {}
        for validator in custom_validators:
            reason = validator(proposal, context, contract_payload)
            if reason is not None:
                return _reject(f"Custom validation failed: {reason}")

    return ValidationVerdict.ACCEPT, DimReasonCode.VALIDATION_PASSED


def _failure_reason_code(failure: InvariantEvaluationFailure) -> str:
    reason = failure.reason
    if isinstance(reason, DimReasonCode):
        return reason.value
    if reason == "INVARIANT_VIOLATION":
        return DimReasonCode.INVARIANT_VIOLATION.value
    return str(reason)


def _reject_invariant_failures(
    context: Dict[str, Any],
    failures: list[InvariantEvaluationFailure],
    reject: Callable[[str | DimReasonCode], ValidationResult],
) -> ValidationResult:
    audit_failures = [
        {
            "invariant_id": failure.invariant_id,
            "reason": _failure_reason_code(failure),
        }
        for failure in failures
    ]
    reason_codes = [_failure_reason_code(failure) for failure in failures]
    joined = ";".join(reason_codes)
    dim_audit = context.setdefault("_dim_audit", {})
    dim_audit["failed_invariant_id"] = failures[0].invariant_id
    dim_audit["failures"] = audit_failures
    return reject(joined)


def _record_rejection_on_fail(
    retry_governor: Optional["IntentRetryGovernor"],
    proposal: PolicyProposal,
    verdict: ValidationVerdict,
) -> None:
    """Record rejection when DIM returns REJECT (for use by callers)."""
    if verdict == ValidationVerdict.REJECT and retry_governor is not None:
        retry_governor.record_rejection(proposal.dfid)
