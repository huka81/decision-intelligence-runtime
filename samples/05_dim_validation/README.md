# 05 - Decision Integrity Module (DIM)

**Goal:** Demonstrate **Policy Validation** through the Decision Integrity Module - ensuring only authorized agents can execute safe policies within valid system states through three-layer validation: Schema, RBAC, and State Consistency.

**DIR Alignment:** DIR Architectural Pattern §6 (Decision Integrity Module), DIR Topologies §3.1 (Policy Validation)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **Decision Integrity Module** | §6 | Central validation gateway for all PolicyProposals |
| **Schema Validation** | §6.1 | Structural checks: required fields present, types correct |
| **RBAC** | §6.2 | Role-Based Access Control: agent_id against allowed list |
| **State Consistency** | §6.3 | Business logic validation against current context/state |
| **Validation Verdict** | §6.4 | Binary outcome: ACCEPT or REJECT with reason |
| **Defense in Depth** | §6 | Multiple validation layers prevent unsafe executions |
| **Context-Aware Rules** | §6.3 | Validation logic considers system state (e.g., risk_score) |
| **Audit Trail** | §6.4 | Every validation produces explicit verdict and reasoning |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Decision Integrity Module (DIM)                   │
│  "Validate PolicyProposals before execution - Defense in Depth"     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Input: PolicyProposal + Context + Allowed Agents                   │
│                                                                     │
│         ↓                                                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 1: SCHEMA VALIDATION                                 │    │
│  │  • Required fields present? (policy_kind, agent_id, etc.)   │    │
│  │  • Valid types and structure?                               │    │
│  │  • Confidence in valid range [0, 1]?                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│         ↓ Pass                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 2: RBAC (Role-Based Access Control)                  │    │
│  │  • Is agent_id in allowed_agents list?                      │    │
│  │  • Does agent have permission for this policy_kind?         │    │
│  │  • Prevent unauthorized or compromised agents               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│         ↓ Pass                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 3: STATE CONSISTENCY                                 │    │
│  │  • Is system in valid state for this policy?                │    │
│  │  • Business logic checks (e.g., risk_score thresholds)      │    │
│  │  • Context-aware rules (no prod deploy if risk > 0.8)       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│         ↓ Pass                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ValidationResult                                           │    │
│  │  • Verdict: ACCEPT or REJECT                                │    │
│  │  • Reason: Explicit explanation                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  If ANY layer fails → REJECT with reason                            │
│  All layers pass → ACCEPT                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## How to run

From repo root:

```bash
pip install -e .
python samples/05_dim_validation/run.py
```

## Scenarios Demonstrated

### Test 1: Normal Operation (ACCEPT)
- **Setup**: Authorized agent (`agent_trading_v1`) in allowed list
- **Context**: Low risk environment (`risk_score: 0.1`)
- **Proposal**: Standard trade execution with high confidence (0.9)
- **Validation**:
  - ✅ Schema: All required fields present
  - ✅ RBAC: Agent in allowed list
  - ✅ State: Risk score acceptable
- **Verdict**: **ACCEPT** - "Validation passed"

### Test 2: Unauthorized Agent (REJECT via RBAC)
- **Setup**: Unknown agent (`agent_hacker_or_bug`) **not** in allowed list
- **Context**: Normal risk environment
- **Proposal**: Emergency shutdown attempt
- **Validation**:
  - ✅ Schema: Valid structure
  - ❌ **RBAC FAILURE**: Agent not authorized
  - (Layer 3 not reached)
- **Verdict**: **REJECT** - "Agent 'agent_hacker_or_bug' not authorized (RBAC)"

### Test 3: High Risk Deployment (REJECT via State Consistency)
- **Setup**: Authorized admin agent (`agent_admin`)
- **Context**: **High risk** environment (`risk_score: 0.95`)
- **Proposal**: Production deployment
- **Validation**:
  - ✅ Schema: Valid structure
  - ✅ RBAC: Agent authorized
  - ❌ **STATE FAILURE**: Risk score (0.95) exceeds threshold (0.8) for production deployment
- **Verdict**: **REJECT** - "Risk score 0.95 too high for deployment"

## Key Functions

```python
from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal

# Create a proposal
proposal = PolicyProposal(
    dfid="dfid_test_1",
    policy_kind="standard_trade",
    agent_id="agent_trading_v1",
    reasoning="Market conditions normal",
    confidence=0.9,
    params={"symbol": "BTC-USD", "action": "BUY"}
)

# Prepare context (from ContextStore)
context = {
    "state": {
        "risk_score": 0.1
    }
}

# Define allowed agents (RBAC)
allowed_agents = ["agent_trading_v1", "agent_admin"]

# Validate
verdict, reason = validate_proposal(proposal, context, allowed_agents)
# Returns: ("ACCEPT", "Validation passed") or ("REJECT", "Reason...")

if verdict == "ACCEPT":
    # Proceed with policy execution
    execute_policy(proposal)
else:
    # Log rejection, possibly escalate
    logger.warning(f"Policy rejected: {reason}")
```

## Expected Output

```
======================================================================
Decision Integrity Module (DIM) Demonstration
======================================================================

[Test 1: Normal Operation] Checking proposal: standard_trade by agent_trading_v1
   Verdict: ✅ ACCEPT
   Reason:  Validation passed

[Test 2: Unauthorized Agent] Checking proposal: emergency_shutdown by agent_hacker_or_bug
   Verdict: ❌ REJECT
   Reason:  Agent 'agent_hacker_or_bug' not authorized (RBAC)
   ⚠️  FAILURE: Should have rejected unauthorized agent!

[Test 3: High Risk Deploy] Checking proposal: deploy_to_production by agent_admin
   Verdict: ❌ REJECT
   Reason:  Risk score 0.95 too high for deployment
   (Correctly rejected due to risk_score > 0.8)

======================================================================
End of Demonstration
```

## Why DIM Matters

from dir_core Architectural Pattern §6:

> *"The Decision Integrity Module (DIM) is the gatekeeper between policy proposals and execution. It enforces defense-in-depth through three validation layers: schema (structural correctness), RBAC (authorization), and state consistency (business logic). Without DIM, a compromised or buggy agent could emit dangerous policies that execute unchecked, leading to financial loss, compliance violations, or system damage."*

### Key Insights:

1. **Defense in Depth**:
   - Multiple validation layers catch different failure modes
   - If one layer has a bug, others provide backup protection
   - Schema catches malformed proposals, RBAC catches unauthorized agents, State catches unsafe contexts

2. **RBAC (Role-Based Access Control)**:
   - Centralized allowed agent registry
   - Prevents compromised or buggy agents from executing policies
   - Example: Junior agent can't trigger production deployments
   - Easy to audit: "Who is allowed to do what?"

3. **State Consistency**:
   - Context-aware validation rules
   - Business logic enforcement (risk thresholds, compliance rules)
   - Prevents valid agents from doing the right thing at the wrong time
   - Example: No deployments during high-risk periods (market volatility, system alerts)

4. **Explicit Verdicts**:
   - Binary outcome: ACCEPT or REJECT (no ambiguity)
   - Every decision includes reasoning for auditability
   - Clear feedback for debugging and compliance reporting

5. **Fail-Safe Design**:
   - Default to REJECT on any validation layer failure
   - Explicit allow list (RBAC) vs. implicit deny
   - Conservative approach protects system integrity

### Real-World Examples:

**Financial Trading**:
- Schema: Ensure order has symbol, quantity, price
- RBAC: Only `agent_execution_v2` can place real trades
- State: Block trades if `market_volatility > 0.9` or `portfolio_leverage > 2.0`

**Cloud Infrastructure**:
- Schema: Deployment has valid config, version, environment
- RBAC: Only `agent_devops_lead` can deploy to production
- State: Block deployments if `incident_count > 0` or `health_check_failure_rate > 0.05`

**Insurance Underwriting**:
- Schema: Application has required fields (age, coverage, history)
- RBAC: Only `agent_senior_underwriter` can approve high-value policies
- State: Block approvals if `fraud_risk_score > 0.7` or `policy_value > agent_authority_limit`

**Healthcare Diagnosis**:
- Schema: Diagnosis has ICD code, confidence, supporting evidence
- RBAC: Only `agent_licensed_physician` can prescribe controlled substances
- State: Block prescriptions if `drug_interaction_risk > 0.8` or `patient_allergy_match`

### Comparison to Alternatives:

❌ **No validation**: Agents execute unchecked → catastrophic failures  
❌ **Agent self-validation**: Each agent implements own checks → inconsistent, hard to audit  
❌ **Post-execution validation**: Damage already done, rollback expensive  
✅ **Centralized DIM**: Consistent enforcement, auditable, fail-safe

### Integration with DIR Pattern:

```
Agent → PolicyProposal 
         ↓
      [DIM Validates] ← Context (risk_score, system_state)
         ↓              ← RBAC (allowed_agents)
    ACCEPT or REJECT
         ↓
    (If ACCEPT) → Execution Runtime
    (If REJECT) → Escalation / Logging
```

The DIM sits between proposal generation and execution, ensuring safety without slowing down the decision pipeline (validation is fast, typically <1ms).

