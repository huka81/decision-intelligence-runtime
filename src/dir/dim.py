"""
Decision Integrity Module (DIM): schema + RBAC + state consistency.

DIR §6. Validates PolicyProposal; returns ACCEPT/REJECT with reason.
Ensures that only authorized agents can execute specific policies within safe bounds.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple

from .models import PolicyProposal

if TYPE_CHECKING:
    from .intent_retry import IntentRetryGovernor

ValidationVerdict = Literal["ACCEPT", "REJECT"]
ValidationResult = Tuple[ValidationVerdict, str]


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
) -> ValidationResult:
    """
    Validate a PolicyProposal against schema, RBAC, TTL, and context state.

    Checks:
    0. Intent Retry Governor: REASONING_EXHAUSTION if max retries exceeded.
    1. Schema: Required fields present.
    2. TTL: valid_until or validity_window_sec (DIR §6.4).
    3. RBAC: Agent ID is in allowed list (if provided).
    4. State: Business logic checks (stub: risk_factor < 0.9).
    """
    now = now or datetime.now(timezone.utc)

    # 0. Intent Retry Governor (DIR §6.2)
    if retry_governor is not None and retry_governor.should_abort(proposal.dfid):
        return "REJECT", "REASONING_EXHAUSTION"

    def _reject(reason: str) -> ValidationResult:
        if retry_governor is not None:
            retry_governor.record_rejection(proposal.dfid)
        return "REJECT", reason

    # 1. Schema Validation
    if not proposal.policy_kind:
        return _reject("Missing policy_kind")
    if not proposal.agent_id:
        return _reject("Missing agent_id")

    # 2. TTL / Decision Validity Window (DIR §6.4)
    valid_until = _resolve_valid_until(proposal)
    if valid_until is not None and now > valid_until:
        return _reject("TTL_EXPIRED")

    # 3. RBAC (Role-Based Access Control)
    if allowed_agents is not None:
        if proposal.agent_id not in allowed_agents:
            return _reject(f"Agent '{proposal.agent_id}' not authorized (RBAC)")

    # 4. Context/State Consistency
    # Example: Check if risk score in context is too high for this policy
    # We assume 'context' structure from ContextStore (has 'state')
    state = context.get("state", {})
    risk_score = state.get("risk_score", 0.0)

    # Example rule: High-risk agents cannot execute 'deploy_to_production' if risk > 0.8
    if proposal.policy_kind == "deploy_to_production" and risk_score > 0.8:
        return _reject(f"Risk score {risk_score} too high for deployment")

    return "ACCEPT", "Validation passed"


def _record_rejection_on_fail(
    retry_governor: Optional["IntentRetryGovernor"],
    proposal: PolicyProposal,
    verdict: str,
) -> None:
    """Record rejection when DIM returns REJECT (for use by callers)."""
    if verdict == "REJECT" and retry_governor is not None:
        retry_governor.record_rejection(proposal.dfid)
