"""
Decision Integrity Module (DIM): schema + RBAC + state consistency.

DIR §6. Validates PolicyProposal; returns ACCEPT/REJECT with reason.
Ensures that only authorized agents can execute specific policies within safe bounds.
"""

from typing import Any, Dict, List, Literal, Optional, Tuple

from .models import PolicyProposal

ValidationVerdict = Literal["ACCEPT", "REJECT"]
ValidationResult = Tuple[ValidationVerdict, str]


def validate_proposal(
    proposal: PolicyProposal, 
    context: Dict[str, Any], 
    allowed_agents: Optional[List[str]] = None
) -> ValidationResult:
    """
    Validate a PolicyProposal against schema, RBAC, and context state.
    
    Checks:
    1. Schema: Required fields present.
    2. RBAC: Agent ID is in allowed list (if provided).
    3. State: Business logic checks (stub: risk_factor < 0.9).
    """
    
    # 1. Schema Validation
    if not proposal.policy_kind:
        return "REJECT", "Missing policy_kind"
    if not proposal.agent_id:
        return "REJECT", "Missing agent_id"
    
    # 2. RBAC (Role-Based Access Control)
    if allowed_agents is not None:
        if proposal.agent_id not in allowed_agents:
            return "REJECT", f"Agent '{proposal.agent_id}' not authorized (RBAC)"

    # 3. Context/State Consistency
    # Example: Check if risk score in context is too high for this policy
    # We assume 'context' structure from ContextStore (has 'state')
    state = context.get("state", {})
    risk_score = state.get("risk_score", 0.0)
    
    # Example rule: High-risk agents cannot execute 'deploy_prod' if risk > 0.8
    if proposal.policy_kind == "deploy_to_production" and risk_score > 0.8:
        return "REJECT", f"Risk score {risk_score} too high for deployment"

    return "ACCEPT", "Validation passed"
