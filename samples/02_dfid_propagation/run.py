#!/usr/bin/env python3
"""
02_dfid - DecisionFlow ID (DFID) as full lifecycle correlation mechanism.

Demonstrates:
- DFID as correlation ID linking all stages of a decision (DIR §5.4)
- DecisionFlow as a container aggregating reasoning + validation + execution
- ContextSnapshot binding (frozen reality at decision time)
- Parent-Child DFID hierarchy for sub-decisions
- Timeline reconstruction for auditability
- Multi-agent correlation within single flow

DIR Manifesto alignment: §5.4 (DecisionFlow and Correlation)
DIR Topologies alignment: §2.2 (ContextSnapshotID), §2.4 (Mesh Decision Lifecycle)

Run from repo root: python samples/02_dfid/run.py
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dir_runtime import (
    ContextSnapshot,
    DecisionFlow,
    EscalationRequest,
    ExecutionIntent,
    ExplainResult,
    Policy,
    PolicyProposal,
    new_dfid,
    new_dfid_with_parent,
)
from dir_runtime.logging_utils import log_with_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# Simulated DIR Components
# =============================================================================


class ContextStore:
    """Simulated Context Store - provides frozen snapshots of relevant state."""
    
    @staticmethod
    def get_market_context() -> Dict[str, Any]:
        """Return current market context."""
        return {
            "instrument": "BTC-USD",
            "price": 67500.00,
            "volatility": 0.025,
            "trend": "bullish",
            "volume_24h": 1_250_000_000,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    @staticmethod
    def get_position_context(position_id: str) -> Dict[str, Any]:
        """Return context for specific position."""
        return {
            "position_id": position_id,
            "entry_price": 65000.00,
            "current_price": 67500.00,
            "size": 0.5,
            "unrealized_pnl": 1250.00,
            "drawdown": 0.0,
        }


class DecisionIntegrityModule:
    """Simulated DIM - validates proposals before execution (DIR §5.1).
    
    Performs Just-In-Time verification to ensure proposal is still valid.
    """
    
    @staticmethod
    def validate(
        proposal: PolicyProposal, 
        context_snapshot: ContextSnapshot,
        flow: DecisionFlow
    ) -> tuple[bool, str]:
        """Validate proposal against current state.
        
        Returns (is_valid, reason).
        """
        # Simulate validation checks
        flow.add_event("VALIDATION", f"DIM validating: {proposal.policy_kind}", details={"proposal_id": proposal.dfid})
        
        # Check 1: Context drift (JIT verification)
        if proposal.context_ref != context_snapshot.snapshot_id:
            return False, f"Context drift: expected {proposal.context_ref}, got {context_snapshot.snapshot_id}"
        
        # Check 2: Confidence threshold
        if proposal.confidence < 0.6:
            return False, f"Confidence too low: {proposal.confidence:.2f} < 0.6"
        
        # Check 3: Policy kind validation
        valid_kinds = ["OPEN_POSITION", "CLOSE_POSITION", "ADJUST_RISK", "HOLD", "TAKE_PROFIT"]
        if proposal.policy_kind not in valid_kinds:
            return False, f"Invalid policy kind: {proposal.policy_kind}"
        
        flow.add_event("VALIDATION", "DIM validation passed", details={"result": "PASS"})
        return True, "All checks passed"


class ExecutionEngine:
    """Simulated Execution Engine - applies validated intents (DIR §5.2)."""
    
    @staticmethod
    def execute(intent: ExecutionIntent, flow: DecisionFlow) -> Dict[str, Any]:
        """Execute the validated intent."""
        flow.record_execution(intent)
        
        # Simulate execution
        result = {
            "executed": True,
            "intent_id": intent.idempotency_key,
            "policy_kind": intent.policy_kind,
            "execution_time_ms": 45,
        }
        
        return result


# =============================================================================
# Simulated Agent (simplified for DFID demonstration)
# =============================================================================


class SimpleAgent:
    """Simplified agent to demonstrate DFID correlation across lifecycle stages."""
    
    def __init__(self, agent_id: str, mission: str):
        self.agent_id = agent_id
        self.mission = mission
    
    def explain(self, dfid: str, context: Dict[str, Any]) -> ExplainResult:
        """Explain stage - interpret context."""
        log_with_dfid(logger, dfid, logging.INFO, f"[{self.agent_id}] Explain stage")
        
        signals = []
        risks = []
        opportunities = []
        
        # Interpret context
        if context.get("trend") == "bullish":
            signals.append("Bullish trend detected")
            opportunities.append("Momentum continuation opportunity")
        
        if context.get("volatility", 0) > 0.03:
            risks.append("Elevated volatility")
        
        if context.get("unrealized_pnl", 0) > 1000:
            opportunities.append("Profit taking opportunity")
        
        return ExplainResult(
            dfid=dfid,
            agent_id=self.agent_id,
            narrative=f"Market context analyzed per mission: {self.mission}",
            identified_signals=signals,
            risks=risks,
            opportunities=opportunities,
            context_summary=context,
        )
    
    def formulate_policy(self, dfid: str, explain: ExplainResult) -> Policy:
        """Policy stage - propose action based on interpretation."""
        log_with_dfid(logger, dfid, logging.INFO, f"[{self.agent_id}] Policy stage")
        
        # Determine action based on signals
        if explain.opportunities and not explain.risks:
            action = "TAKE_PROFIT"
            confidence = 0.85
            justification = "Profit opportunity with low risk"
        elif explain.risks:
            action = "HOLD"
            confidence = 0.65
            justification = "Risk detected, maintaining position"
        else:
            action = "HOLD"
            confidence = 0.70
            justification = "No clear signal"
        
        return Policy(
            dfid=dfid,
            agent_id=self.agent_id,
            proposed_action=action,
            justification=justification,
            confidence=confidence,
            assumptions=["Market structure unchanged", "No major news events"],
            expected_outcomes=["Position maintained or profit secured"],
        )
    
    def emit_proposal(self, dfid: str, policy: Policy, context_ref: str) -> PolicyProposal:
        """Emit PolicyProposal for DIM validation."""
        log_with_dfid(logger, dfid, logging.INFO, f"[{self.agent_id}] Emitting proposal: {policy.proposed_action}")
        
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy.proposed_action,
            params={"justification": policy.justification},
            context_ref=context_ref,
            confidence=policy.confidence,
            justification=policy.justification,
        )


# =============================================================================
# DecisionFlow Registry (tracks all flows)
# =============================================================================


class FlowRegistry:
    """Simple registry to track all DecisionFlows in the system."""
    
    def __init__(self):
        self._flows: Dict[str, DecisionFlow] = {}
    
    def create_flow(self, dfid: Optional[str] = None, parent_dfid: Optional[str] = None) -> DecisionFlow:
        """Create and register a new flow."""
        if dfid is None:
            dfid = new_dfid() if parent_dfid is None else new_dfid_with_parent(parent_dfid)
        
        flow = DecisionFlow(dfid=dfid, parent_dfid=parent_dfid)
        flow.add_event("FLOW_STARTED", f"Flow created{' (child of ' + parent_dfid + ')' if parent_dfid else ''}")
        
        self._flows[dfid] = flow
        
        # Track in parent
        if parent_dfid and parent_dfid in self._flows:
            self._flows[parent_dfid].create_child_flow(dfid)
        
        return flow
    
    def get_flow(self, dfid: str) -> Optional[DecisionFlow]:
        return self._flows.get(dfid)
    
    def get_all_flows(self) -> Dict[str, DecisionFlow]:
        return self._flows.copy()


# =============================================================================
# Main Demonstration
# =============================================================================


def main() -> None:
    print("=" * 70)
    print("DFID Sample - DecisionFlow as Full Lifecycle Correlation")
    print("=" * 70)
    
    registry = FlowRegistry()
    dim = DecisionIntegrityModule()
    executor = ExecutionEngine()
    
    # -------------------------------------------------------------------------
    # Scenario A: Complete Decision Lifecycle with DFID Correlation
    # -------------------------------------------------------------------------
    
    print("\n[SCENARIO A] Complete lifecycle - single flow, single agent\n")
    
    # 1. Create flow
    flow_a = registry.create_flow()
    dfid_a = flow_a.dfid
    log_with_dfid(logger, dfid_a, logging.INFO, "Starting Scenario A")
    
    # 2. Capture context snapshot
    market_ctx = ContextStore.get_market_context()
    snapshot_a = ContextSnapshot.create(dfid_a, market_ctx, source="market_data")
    flow_a.set_context(snapshot_a)
    log_with_dfid(logger, dfid_a, logging.INFO, f"Context snapshot: {snapshot_a.snapshot_id}")
    
    # 3. Agent reasoning cycle
    agent = SimpleAgent("strategy_agent", "Optimize returns with controlled risk")
    
    explain_result = agent.explain(dfid_a, market_ctx)
    flow_a.record_explain(explain_result)
    
    policy = agent.formulate_policy(dfid_a, explain_result)
    flow_a.record_policy(policy)
    
    # 4. Self-check & emit proposal
    proposal = agent.emit_proposal(dfid_a, policy, snapshot_a.snapshot_id)
    flow_a.record_proposal(proposal)
    
    # 5. DIM validation
    valid, reason = dim.validate(proposal, snapshot_a, flow_a)
    log_with_dfid(logger, dfid_a, logging.INFO, f"DIM validation: {reason}")
    
    # 6. Execution
    if valid:
        intent = ExecutionIntent(
            dfid=dfid_a,
            idempotency_key=f"{dfid_a}:{proposal.policy_kind}",
            policy_kind=proposal.policy_kind,
            params=proposal.params,
        )
        result = executor.execute(intent, flow_a)
        flow_a.complete(f"Executed {proposal.policy_kind} successfully")
    else:
        flow_a.abort(f"Validation failed: {reason}")
    
    print(f"\n  Flow completed with status: {flow_a.status}")
    print(f"  Participating agents: {flow_a.participating_agents}")
    print(f"  Timeline events: {len(flow_a.timeline)}")
    
    # -------------------------------------------------------------------------
    # Scenario B: Parent-Child Flow Hierarchy
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO B] Parent-Child DFID hierarchy - delegated sub-decision\n")
    
    # Parent flow: Strategic decision
    parent_flow = registry.create_flow()
    parent_dfid = parent_flow.dfid
    log_with_dfid(logger, parent_dfid, logging.INFO, "Parent flow: Portfolio rebalancing decision")
    
    parent_ctx = ContextStore.get_market_context()
    parent_snapshot = ContextSnapshot.create(parent_dfid, parent_ctx, source="portfolio_view")
    parent_flow.set_context(parent_snapshot)
    
    strategy_agent = SimpleAgent("portfolio_agent", "Balance risk across positions")
    parent_explain = strategy_agent.explain(parent_dfid, parent_ctx)
    parent_flow.record_explain(parent_explain)
    
    # Delegate to child flow for position-specific decision
    log_with_dfid(logger, parent_dfid, logging.INFO, "Delegating to child flow for position POS_001")
    
    child_flow = registry.create_flow(parent_dfid=parent_dfid)
    child_dfid = child_flow.dfid
    log_with_dfid(logger, child_dfid, logging.INFO, "Child flow: Position-specific decision")
    
    position_ctx = ContextStore.get_position_context("POS_001")
    child_snapshot = ContextSnapshot.create(child_dfid, position_ctx, source="position_tracker")
    child_flow.set_context(child_snapshot)
    
    position_agent = SimpleAgent("position_agent", "Manage individual position risk")
    child_explain = position_agent.explain(child_dfid, position_ctx)
    child_flow.record_explain(child_explain)
    
    child_policy = position_agent.formulate_policy(child_dfid, child_explain)
    child_flow.record_policy(child_policy)
    
    child_proposal = position_agent.emit_proposal(child_dfid, child_policy, child_snapshot.snapshot_id)
    child_flow.record_proposal(child_proposal)
    
    valid, reason = dim.validate(child_proposal, child_snapshot, child_flow)
    if valid:
        intent = ExecutionIntent(
            dfid=child_dfid,
            idempotency_key=f"{child_dfid}:{child_proposal.policy_kind}",
            policy_kind=child_proposal.policy_kind,
            params=child_proposal.params,
        )
        executor.execute(intent, child_flow)
        child_flow.complete(f"Position action: {child_proposal.policy_kind}")
    
    # Complete parent after child
    parent_flow.complete("Delegation completed successfully")
    
    print(f"\n  Parent DFID: {parent_dfid[:12]}...")
    print(f"  Child DFID:  {child_dfid[:12]}...")
    print(f"  Parent tracks child: {parent_flow.child_dfids}")
    print(f"  Child knows parent: {child_flow.parent_dfid[:12]}...")
    
    # -------------------------------------------------------------------------
    # Scenario C: Multi-Agent Collaboration in Single Flow
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO C] Multi-agent collaboration - same DFID, multiple agents\n")
    
    multi_flow = registry.create_flow()
    multi_dfid = multi_flow.dfid
    log_with_dfid(logger, multi_dfid, logging.INFO, "Multi-agent flow started")
    
    shared_ctx = ContextStore.get_market_context()
    shared_snapshot = ContextSnapshot.create(multi_dfid, shared_ctx, source="shared_context")
    multi_flow.set_context(shared_snapshot)
    
    # Multiple agents contribute Explain results
    agents = [
        SimpleAgent("risk_monitor", "Identify and quantify risks"),
        SimpleAgent("sentiment_agent", "Analyze market sentiment"),
        SimpleAgent("technical_agent", "Technical analysis signals"),
    ]
    
    for agent in agents:
        explain = agent.explain(multi_dfid, shared_ctx)
        multi_flow.record_explain(explain)
        time.sleep(0.01)  # Simulate parallel execution
    
    # Final decision by strategy agent
    decider = SimpleAgent("strategy_decider", "Aggregate insights and decide")
    final_explain = decider.explain(multi_dfid, shared_ctx)
    multi_flow.record_explain(final_explain)
    
    final_policy = decider.formulate_policy(multi_dfid, final_explain)
    multi_flow.record_policy(final_policy)
    
    final_proposal = decider.emit_proposal(multi_dfid, final_policy, shared_snapshot.snapshot_id)
    multi_flow.record_proposal(final_proposal)
    
    multi_flow.complete("Multi-agent consensus reached")
    
    print(f"\n  Single DFID: {multi_dfid[:12]}...")
    print(f"  Participating agents: {multi_flow.participating_agents}")
    print(f"  Total Explain results: {len(multi_flow.explain_results)}")
    
    # -------------------------------------------------------------------------
    # Scenario D: Escalation with DFID Tracing
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO D] Escalation - tracked in flow for audit\n")
    
    esc_flow = registry.create_flow()
    esc_dfid = esc_flow.dfid
    log_with_dfid(logger, esc_dfid, logging.INFO, "Escalation scenario started")
    
    esc_ctx = {"instrument": "BTC-USD", "volatility": 0.08, "trend": "unclear"}
    esc_snapshot = ContextSnapshot.create(esc_dfid, esc_ctx, source="volatile_market")
    esc_flow.set_context(esc_snapshot)
    
    uncertain_agent = SimpleAgent("cautious_agent", "Act only with high confidence")
    uncertain_explain = uncertain_agent.explain(esc_dfid, esc_ctx)
    esc_flow.record_explain(uncertain_explain)
    
    # Agent decides to escalate due to uncertainty
    escalation = EscalationRequest(
        dfid=esc_dfid,
        from_agent_id="cautious_agent",
        to_agent_id="supervisor",
        trigger="uncertainty_threshold",
        severity="MEDIUM",
        context=esc_ctx,
    )
    esc_flow.record_escalation(escalation)
    log_with_dfid(logger, esc_dfid, logging.INFO, f"Escalated: {escalation.trigger}")
    
    print(f"\n  Flow status: {esc_flow.status}")
    print(f"  Escalation recorded in flow timeline")
    
    # =========================================================================
    # Summary: Timeline Reports
    # =========================================================================
    
    print("\n" + "=" * 70)
    print("[SUMMARY] DecisionFlow Timeline Reports")
    print("=" * 70)
    
    # Show Scenario A timeline
    print(f"\n{flow_a.get_timeline_report()}")
    
    # Show parent-child relationship
    print(f"\n{'─' * 50}")
    print(f"Parent Flow: {parent_dfid}")
    print(f"  → Child Flows: {parent_flow.child_dfids}")
    
    # Registry summary
    print(f"\n{'─' * 50}")
    print("Flow Registry Summary:")
    for dfid, flow in registry.get_all_flows().items():
        parent_info = f" (child of {flow.parent_dfid[:8]}...)" if flow.parent_dfid else ""
        print(f"  {dfid[:12]}... [{flow.status}] agents={len(flow.participating_agents)}{parent_info}")
    
    # Grep hint
    print(f"\n{'─' * 50}")
    print("Traceability hint:")
    print(f"  grep '[DFID={flow_a.dfid}]' to trace Scenario A")
    print(f"  All events for a DFID can be reconstructed from DecisionFlow.timeline")


if __name__ == "__main__":
    main()
