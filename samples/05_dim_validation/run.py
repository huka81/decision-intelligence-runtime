#!/usr/bin/env python3
"""
05_dim_validation - Demonstrates Decision Integrity Module (DIR §6).

Shows:
1. Schema Validation (structure).
2. RBAC (Role-Based Access Control) - strictly allowed list.
3. State Consistency - e.g. blocking risky actions if context indicates high risk.
"""

import logging
from typing import Dict, Any

from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_check(test_name: str, proposal: PolicyProposal, context: Dict[str, Any], allowed_agents: list = None):
    print(f"\n[{test_name}] Checking proposal: {proposal.policy_kind} by {proposal.agent_id}")
    verdict, reason = validate_proposal(proposal, context, allowed_agents)
    
    icon = "[OK]" if verdict == "ACCEPT" else "[NO]"
    print(f"   Verdict: {icon} {verdict}")
    print(f"   Reason:  {reason}")
    return verdict


def main() -> None:
    print("=" * 70)
    print("Decision Integrity Module (DIM) Demonstration")
    print("=" * 70)

    # Scenarios
    
    # 1. Valid Proposal
    p1 = PolicyProposal(
        dfid="dfid_test_1",
        policy_kind="standard_trade",
        agent_id="agent_trading_v1",
        reasoning="Market conditions normal",
        confidence=0.9,
        params={"symbol": "BTC-USD", "action": "BUY"}
    )
    ctx_normal = {"state": {"risk_score": 0.1}}
    allowed = ["agent_trading_v1", "agent_admin"]
    
    run_check("Test 1: Normal Operation", p1, ctx_normal, allowed)

    # 2. Unauthorized Agent (RBAC)
    p2 = PolicyProposal(
        dfid="dfid_test_2",
        policy_kind="emergency_shutdown",
        agent_id="agent_hacker_or_bug", # Not in allowed list
        reasoning="Trying to stop system",
        confidence=1.0,
        params={}
    )
    
    verdict = run_check("Test 2: Unauthorized Agent", p2, ctx_normal, allowed)
    if verdict != "REJECT":
        print("   WARNING: FAILURE: Should have rejected unauthorized agent!")

    # 3. High Risk Context (State Consistency)
    # Applying 'deploy_to_production' when risk is high
    p3 = PolicyProposal(
        dfid="dfid_test_3",
        policy_kind="deploy_to_production",
        agent_id="agent_admin",
        reasoning="Weekly release",
        confidence=1.0,
        params={"version": "1.2.0"}
    )
    ctx_risky = {"state": {"risk_score": 0.95}} # > 0.8 threshold
    
    verdict = run_check("Test 3: High Risk Deploy", p3, ctx_risky, allowed)
    if verdict != "REJECT":
        print("   WARNING: FAILURE: Should have rejected high-risk deployment!")
    else:
        print("   (Correctly rejected due to risk_score > 0.8)")

    print("\n" + "=" * 70)
    print("End of Demonstration")


if __name__ == "__main__":
    main()

