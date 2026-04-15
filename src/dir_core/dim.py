"""
Decision Integrity Module (DIM): schema + RBAC + state consistency.

DIR §6. Validates PolicyProposal; returns ``ValidationVerdict`` with a reason (``str`` or ``DimReasonCode``).
Ensures that only authorized agents can execute specific policies within safe bounds.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .models import PolicyProposal
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


def validate_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]] = None,
    now: Optional[datetime] = None,
    retry_governor: Optional["IntentRetryGovernor"] = None,
    contract: Optional[Dict[str, Any]] = None,
    custom_validators: Optional[List[Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]]] = None,
) -> ValidationResult:
    """
    Validate a PolicyProposal against schema, RBAC, TTL, generic contract boundaries,
    and custom domain-specific validators.
    """
    now = now or datetime.now(timezone.utc)

    # 0. Intent Retry Governor
    if retry_governor is not None and retry_governor.should_abort(proposal.dfid):
        return ValidationVerdict.REJECT, DimReasonCode.REASONING_EXHAUSTION

    def _reject(reason: str | DimReasonCode) -> ValidationResult:
        if retry_governor is not None:
            retry_governor.record_rejection(proposal.dfid)
        return ValidationVerdict.REJECT, reason

    # 1. Schema Validation
    if not proposal.policy_kind:
        return _reject("Missing policy_kind")
    if not proposal.agent_id:
        return _reject("Missing agent_id")

    # 2. TTL / Decision Validity Window
    valid_until = _resolve_valid_until(proposal)
    if valid_until is not None and now > valid_until:
        return _reject(DimReasonCode.TTL_EXPIRED)

    # 3. RBAC (Role-Based Access Control)
    if allowed_agents is not None:
        if proposal.agent_id not in allowed_agents:
            return _reject(f"Agent '{proposal.agent_id}' not authorized (RBAC)")

    # 4. Generic Contract Boundaries (if contract provided)
    if contract:
        # Handle nested variants (e.g. from samples/00_quick_start) vs flat
        permissions = contract.get("permissions", contract)
        safety_rules = contract.get("safety_rules", contract)

        # 4a. Validate allowed policies
        allowed_policies = permissions.get("allowed_policy_types")
        if allowed_policies is not None and proposal.policy_kind not in allowed_policies:
            return _reject(
                f"Policy '{proposal.policy_kind}' is not in allowed_policy_types: {allowed_policies}"
            )

        # 4b. Validate minimum confidence
        min_conf = safety_rules.get("min_confidence_threshold")
        if min_conf is not None and proposal.confidence < float(min_conf):
            return _reject(
                f"Proposal confidence ({proposal.confidence}) is below threshold ({min_conf})"
            )

    # 4.1. Context/State Consistency (Legacy stub)
    state = context.get("state", {})
    risk_score = state.get("risk_score", 0.0)
    if proposal.policy_kind == "deploy_to_production" and risk_score > 0.8:
        return _reject(f"Risk score {risk_score} too high for deployment")

    # 5. Domain-Specific Validators (Edge cases & business logic)
    if custom_validators:
        for validator in custom_validators:
            # Custom validator returns a string reason if rejected, else None
            reason = validator(proposal, context, contract or {})
            if reason is not None:
                return _reject(f"Custom validation failed: {reason}")

    return ValidationVerdict.ACCEPT, DimReasonCode.VALIDATION_PASSED


def _record_rejection_on_fail(
    retry_governor: Optional["IntentRetryGovernor"],
    proposal: PolicyProposal,
    verdict: ValidationVerdict,
) -> None:
    """Record rejection when DIM returns REJECT (for use by callers)."""
    if verdict == ValidationVerdict.REJECT and retry_governor is not None:
        retry_governor.record_rejection(proposal.dfid)
