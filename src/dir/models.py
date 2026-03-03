"""
Shared Pydantic models: ResponsibilityContract, PolicyProposal, ExecutionIntent, etc.

Aligned with ROA Manifesto §3 and DIR Architectural Pattern §5.

Extended with:
- ExplainResult (§4.1): Structured reasoning output from context interpretation
- Policy (§4.2): Structured recommendation with justification and confidence
- SelfCheckResult (§4.3): Introspection result for boundary validation
- AgentState (§3.4): Long-lived state with decision trajectory and memory
- EscalationRequest (§5.3): Structure for authority escalation
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# ROA Core: Responsibility Contract (Manifesto §3.1)
# =============================================================================


class ResponsibilityContract(BaseModel):
    """ROA: scope, authority, mission, escalation (Manifesto §3.1)."""

    agent_id: str
    role: Literal["STRATEGIST", "EXECUTOR", "MONITOR"] = "EXECUTOR"
    mission: str = ""
    authorized_instruments: List[str] = Field(default_factory=list)
    allowed_policy_types: List[str] = Field(default_factory=list)
    escalate_on_uncertainty: float = 0.7
    # Extended fields for ROA compliance
    max_drawdown_limit: float = Field(default=0.05, description="Maximum drawdown limit (5%)")
    escalation_triggers: List[str] = Field(
        default_factory=lambda: ["uncertainty_threshold", "authority_breach", "risk_limit_exceeded"]
    )
    parent_agent_id: Optional[str] = Field(default=None, description="Parent agent for hierarchy")
    # Wake-up Predicates (DIR Topologies §2.3)
    wake_up_threshold_pct: float = Field(
        default=0.5,
        description="Minimum price change (%) to wake up agent - prevents Token Burn on minor signals"
    )


# =============================================================================
# Decision Lifecycle: Explain → Policy → Self-Check (Manifesto §4)
# =============================================================================


class ExplainResult(BaseModel):
    """ROA: Output of Explain stage - context interpretation (Manifesto §4.1).
    
    Answers: 'What is happening, and why does it matter for my mission?'
    """

    dfid: str
    agent_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    narrative: str = Field(description="Natural language interpretation of the situation")
    identified_signals: List[str] = Field(default_factory=list, description="Relevant patterns detected")
    risks: List[str] = Field(default_factory=list, description="Identified risks")
    opportunities: List[str] = Field(default_factory=list, description="Identified opportunities")
    context_summary: Dict[str, Any] = Field(default_factory=dict, description="Key context facts used")


class Policy(BaseModel):
    """ROA: Structured recommendation from Policy stage (Manifesto §4.2).
    
    A Policy is NOT an action - it's an interpretable recommendation with justification.
    """

    dfid: str
    agent_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    proposed_action: str = Field(description="The recommended course of action")
    justification: str = Field(description="Reasoning rooted in Explain stage")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence/uncertainty indicator")
    assumptions: List[str] = Field(default_factory=list, description="Required assumptions for this policy")
    expected_outcomes: List[str] = Field(default_factory=list, description="Expected results or risks")
    explain_ref: Optional[str] = Field(default=None, description="Reference to ExplainResult")


class SelfCheckResult(BaseModel):
    """ROA: Result of agent self-check before emitting proposal (Manifesto §4.3).
    
    Self-Check is a cost-optimization heuristic - it has no security value.
    Catches obvious issues before reaching the Runtime.
    """

    passed: bool = Field(description="Whether policy passes self-check")
    reason: Optional[str] = Field(default=None, description="Reason if failed")
    should_escalate: bool = Field(default=False, description="Whether to escalate to parent agent")
    escalation_trigger: Optional[str] = Field(default=None, description="Which trigger caused escalation")


# =============================================================================
# Agent State and Memory (Manifesto §3.4)
# =============================================================================


class DecisionRecord(BaseModel):
    """Single decision in agent's trajectory history."""

    dfid: str
    timestamp: datetime = Field(default_factory=_utcnow)
    explain_summary: str = ""
    policy_action: str = ""
    policy_confidence: float = 0.0
    outcome: Literal["ACCEPTED", "REJECTED", "ESCALATED", "PENDING"] = "PENDING"
    outcome_reason: Optional[str] = None


class AgentState(BaseModel):
    """ROA: Long-lived agent state with memory (Manifesto §3.4).
    
    Provides continuity, self-awareness, and trajectory for reasoning.
    """

    agent_id: str
    created_at: datetime = Field(default_factory=_utcnow)
    last_active: datetime = Field(default_factory=_utcnow)
    decision_trajectory: List[DecisionRecord] = Field(
        default_factory=list, description="History of past decisions and rationales"
    )
    policy_version: int = Field(default=1, description="Version of agent's strategy/policy")
    current_context: Dict[str, Any] = Field(default_factory=dict, description="Current operational context")
    is_active: bool = Field(default=True, description="Whether agent is still active in lifecycle")


# =============================================================================
# Escalation (Manifesto §5.3)
# =============================================================================


class EscalationRequest(BaseModel):
    """ROA: Request for escalation to higher-level agent (Manifesto §5.3).
    
    Escalation is not failure - it's essential for bounded responsibility.
    """

    dfid: str
    from_agent_id: str
    to_agent_id: Optional[str] = Field(default=None, description="Target parent agent, if known")
    trigger: str = Field(description="What triggered escalation")
    context: Dict[str, Any] = Field(default_factory=dict)
    original_policy: Optional[Policy] = Field(default=None, description="Policy that couldn't be executed")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"


# =============================================================================
# Policy Proposal and Execution (DIR §5, §7)
# =============================================================================


class PolicyProposal(BaseModel):
    """Structured intent from agent; validated by DIM before execution (DIR §5)."""

    dfid: str
    agent_id: str
    policy_kind: str
    params: Dict[str, Any] = Field(default_factory=dict)
    context_ref: Optional[str] = None
    execution_constraints: Dict[str, Any] = Field(default_factory=dict)
    # Extended fields linking to ROA lifecycle
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    justification: Optional[str] = Field(default=None, description="From Policy stage")
    explain_ref: Optional[str] = Field(default=None, description="Reference to ExplainResult")


class ExecutionIntent(BaseModel):
    """Validated proposal; only this type is authorized to trigger side effects (DIR §7)."""

    dfid: str
    idempotency_key: str
    policy_kind: str
    params: Dict[str, Any] = Field(default_factory=dict)


class DecisionAtom(BaseModel):
    """Decision Atom for Topology B (SDS) — snapshot-bound decision.

    DIR Topologies §3.1.2: The DecisionAtom MUST include snapshot_id hash-binding
    so the JIT Validator can verify state has not drifted since the snapshot.
    """

    dfid: str = Field(description="DecisionFlow ID for correlation")
    snapshot_id: str = Field(
        description="Context snapshot hash for JIT drift check"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Decision payload (action, amount, user_id, etc.)",
    )


class ProofCarryingIntent(BaseModel):
    """Proof-Carrying Intent (PCI) for Topology C (DL+PCI).

    The agent submits this to the DIM. The evidence_hash is a CLAIM; the DIM
    independently recalculates it using authoritative Context and Contract.
    Mismatch = reject (Zero Trust).

    intent_payload: Domain-specific proposal as dict for flexibility.
    Sample 33 uses policy_proposal.model_dump(); DIM uses PolicyProposal.model_validate().
    """

    dfid: str = Field(description="DecisionFlow ID for traceability")
    intent_payload: Dict[str, Any] = Field(
        description="Structured decision (e.g. coverage, premium); domain-specific"
    )
    context_ref: str = Field(
        description="ContextSnapshotID / hash for Evidence Hash binding"
    )
    evidence_hash: str = Field(
        description="SHA256(DFID || Context_Hash || Contract_Hash || Proposal_Params)"
    )
    signature: str = Field(
        default="",
        description="Cryptographic signature (HMAC or placeholder)",
    )


# =============================================================================
# DecisionFlow: Full Lifecycle Correlation (DIR §5.4)
# =============================================================================


class ContextSnapshot(BaseModel):
    """Frozen state of relevant context at a point in time (DIR Topologies §2.2).
    
    ContextSnapshotID is the hash binding, ensuring every PolicyProposal
    is linked to the exact version of the world the agent 'saw'.
    """

    snapshot_id: str = Field(description="Unique hash/ID for this snapshot")
    dfid: str = Field(description="Associated DecisionFlow ID")
    timestamp: datetime = Field(default_factory=_utcnow)
    data: Dict[str, Any] = Field(default_factory=dict, description="Frozen context data")
    source: str = Field(default="context_store", description="Origin of context")
    
    @classmethod
    def create(cls, dfid: str, data: Dict[str, Any], source: str = "context_store") -> "ContextSnapshot":
        """Factory method that generates snapshot_id from content hash."""
        import hashlib
        import json
        content = json.dumps(data, sort_keys=True, default=str)
        snapshot_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        return cls(snapshot_id=snapshot_id, dfid=dfid, data=data, source=source)


class FlowEvent(BaseModel):
    """Single event in a DecisionFlow timeline."""

    timestamp: datetime = Field(default_factory=_utcnow)
    event_type: Literal[
        "FLOW_STARTED",
        "CONTEXT_SNAPSHOT",
        "EXPLAIN",
        "POLICY",
        "SELF_CHECK",
        "PROPOSAL",
        "VALIDATION",
        "EXECUTION",
        "ESCALATION",
        "CHILD_FLOW_CREATED",
        "FLOW_COMPLETED",
        "FLOW_ABORTED",
    ]
    agent_id: Optional[str] = None
    summary: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class DecisionFlow(BaseModel):
    """DIR: Container for the entire decision lifecycle (Manifesto §5.4).
    
    A DecisionFlow aggregates:
    - Initial context (ContextSnapshot)
    - All policy proposals
    - Validation results
    - Escalations
    - Execution events
    - Final outcomes
    
    DFID allows auditability, debugging, compliance reporting, causal reasoning,
    replaying decisions, and clean separation of concurrent decision processes.
    """

    dfid: str = Field(description="The immutable DecisionFlow ID")
    parent_dfid: Optional[str] = Field(default=None, description="Parent flow for hierarchical decisions")
    created_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    
    # Lifecycle artifacts
    context_snapshot: Optional[ContextSnapshot] = None
    explain_results: List[ExplainResult] = Field(default_factory=list)
    policies: List[Policy] = Field(default_factory=list)
    proposals: List[PolicyProposal] = Field(default_factory=list)
    escalations: List[EscalationRequest] = Field(default_factory=list)
    execution_intents: List[ExecutionIntent] = Field(default_factory=list)
    
    # Timeline for reconstruction
    timeline: List[FlowEvent] = Field(default_factory=list)
    
    # Outcome
    status: Literal["IN_PROGRESS", "COMPLETED", "ESCALATED", "ABORTED"] = "IN_PROGRESS"
    outcome_summary: Optional[str] = None
    
    # Participating agents
    participating_agents: List[str] = Field(default_factory=list)
    
    # Child flows (for hierarchical decisions)
    child_dfids: List[str] = Field(default_factory=list)
    
    def add_event(
        self, 
        event_type: str, 
        summary: str, 
        agent_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an event to the timeline."""
        event = FlowEvent(
            event_type=event_type,
            agent_id=agent_id,
            summary=summary,
            details=details or {}
        )
        self.timeline.append(event)
        if agent_id and agent_id not in self.participating_agents:
            self.participating_agents.append(agent_id)
    
    def set_context(self, snapshot: ContextSnapshot) -> None:
        """Bind context snapshot to this flow."""
        self.context_snapshot = snapshot
        self.add_event("CONTEXT_SNAPSHOT", f"Context bound: {snapshot.snapshot_id}", details={"snapshot_id": snapshot.snapshot_id})
    
    def record_explain(self, result: ExplainResult) -> None:
        """Record an Explain stage result."""
        self.explain_results.append(result)
        self.add_event(
            "EXPLAIN", 
            f"Explain: {len(result.identified_signals)} signals, {len(result.risks)} risks",
            agent_id=result.agent_id,
            details={"narrative": result.narrative[:100] + "..." if len(result.narrative) > 100 else result.narrative}
        )
    
    def record_policy(self, policy: Policy) -> None:
        """Record a Policy formation."""
        self.policies.append(policy)
        self.add_event(
            "POLICY",
            f"Policy: {policy.proposed_action} (conf={policy.confidence:.2f})",
            agent_id=policy.agent_id,
            details={"action": policy.proposed_action, "confidence": policy.confidence}
        )
    
    def record_proposal(self, proposal: PolicyProposal) -> None:
        """Record a PolicyProposal emission."""
        self.proposals.append(proposal)
        self.add_event(
            "PROPOSAL",
            f"Proposal: {proposal.policy_kind}",
            agent_id=proposal.agent_id,
            details={"policy_kind": proposal.policy_kind, "confidence": proposal.confidence}
        )
    
    def record_escalation(self, escalation: EscalationRequest) -> None:
        """Record an escalation event."""
        self.escalations.append(escalation)
        self.add_event(
            "ESCALATION",
            f"Escalated: {escalation.trigger} ({escalation.severity})",
            agent_id=escalation.from_agent_id,
            details={"trigger": escalation.trigger, "severity": escalation.severity}
        )
        self.status = "ESCALATED"
    
    def record_execution(self, intent: ExecutionIntent) -> None:
        """Record an execution intent."""
        self.execution_intents.append(intent)
        self.add_event(
            "EXECUTION",
            f"Executed: {intent.policy_kind}",
            details={"idempotency_key": intent.idempotency_key}
        )
    
    def complete(self, summary: str) -> None:
        """Mark flow as completed."""
        self.completed_at = _utcnow()
        self.status = "COMPLETED"
        self.outcome_summary = summary
        self.add_event("FLOW_COMPLETED", summary)
    
    def abort(self, reason: str) -> None:
        """Mark flow as aborted."""
        self.completed_at = _utcnow()
        self.status = "ABORTED"
        self.outcome_summary = reason
        self.add_event("FLOW_ABORTED", reason)
    
    def create_child_flow(self, child_dfid: str) -> None:
        """Record creation of a child flow."""
        self.child_dfids.append(child_dfid)
        self.add_event("CHILD_FLOW_CREATED", f"Child flow: {child_dfid}", details={"child_dfid": child_dfid})
    
    def get_timeline_report(self) -> str:
        """Generate human-readable timeline report."""
        lines = [
            f"═══ DecisionFlow Report ═══",
            f"DFID: {self.dfid}",
            f"Status: {self.status}",
            f"Created: {self.created_at.isoformat()}",
        ]
        if self.parent_dfid:
            lines.append(f"Parent: {self.parent_dfid}")
        if self.context_snapshot:
            lines.append(f"Context: {self.context_snapshot.snapshot_id}")
        lines.append(f"Agents: {', '.join(self.participating_agents) or 'none'}")
        lines.append(f"\n─── Timeline ({len(self.timeline)} events) ───")
        
        for i, event in enumerate(self.timeline, 1):
            time_str = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
            agent_str = f" [{event.agent_id}]" if event.agent_id else ""
            lines.append(f"  {i:2}. [{time_str}] {event.event_type}{agent_str}: {event.summary}")
        
        if self.outcome_summary:
            lines.append(f"\n─── Outcome ───")
            lines.append(f"  {self.outcome_summary}")
        
        return "\n".join(lines)

