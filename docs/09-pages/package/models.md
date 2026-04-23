---
title: Models & DTOs
nav_order: 6
---

# Models & Data Transfer Objects (DTOs)

Communication across "The Wall" (between User Space and Kernel Space) requires highly structured, strict data formats. `dir-core` leverages `pydantic` to define these objects as pure Data Transfer Objects (DTOs).

## `ResponsibilityContract`

Defines the absolute boundaries of an agent. This is not a system prompt—it is a deterministic structure validated by the DIM.

```python
class ResponsibilityContract(BaseModel):
    agent_id: str
    role: ContractRole = ContractRole.EXECUTOR
    mission: str = ""
    authorized_instruments: List[str] = Field(default_factory=list)
    allowed_policy_types: List[str] = Field(default_factory=list)
    escalate_on_uncertainty: float = 0.7
    max_drawdown_limit: float = Field(default=0.05)
```

## `PolicyProposal` (The Claim)

Produced by the Agent in User Space. This represents *intent* and is entirely untrusted until validated.

```python
class PolicyProposal(BaseModel):
    dfid: str
    agent_id: str
    policy_kind: str
    params: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    justification: Optional[str] = None
    # JIT verification
    context_ref: Optional[str] = None
    valid_until: Optional[datetime] = None
```

## `ExecutionIntent` (The Fact)

If the DIM accepts a `PolicyProposal`, it converts it into an `ExecutionIntent`. This is the **only** object authorized to be passed to infrastructure adapters for external execution (like API calls).

```python
class ExecutionIntent(BaseModel):
    dfid: str
    idempotency_key: str
    policy_kind: str
    params: Dict[str, Any] = Field(default_factory=dict)
```

> **Idempotency Guard**: Notice that the `ExecutionIntent` contains an `idempotency_key`. The `dir-core` Kernel guarantees this key is generated via an exact formula: `SHA256(DFID + Step_ID + Canonical_Params)`. This prevents duplicate executions even if the agent loops or retries.

## `DecisionFlow` & `DFID`

The `DecisionFlow ID` (`DFID`) is the unique identifier tracking a decision's entire lifecycle. A `DecisionFlow` object aggregates all elements of the process.

```python
class DecisionFlow(BaseModel):
    dfid: str
    parent_dfid: Optional[str] = None
    status: DecisionFlowStatus = DecisionFlowStatus.IN_PROGRESS
    
    # Lifecycle artifacts
    context_snapshot: Optional[ContextSnapshot] = None
    policies: List[Policy] = Field(default_factory=list)
    proposals: List[PolicyProposal] = Field(default_factory=list)
    escalations: List[EscalationRequest] = Field(default_factory=list)
    execution_intents: List[ExecutionIntent] = Field(default_factory=list)
    
    # Audit trail
    timeline: List[FlowEvent] = Field(default_factory=list)
```

Every log emitted by `dir-core` or the Application space should include the `DFID` to ensure 100% causal reconstructability during audits.
