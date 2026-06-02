# Problem Specification: Autonomous Flight Delay Refund System

**Document Type:** Compiler Instruction Set — Domain Model & Requirements  
**Architecture:** DIR Topology C (Decision Ledger with Proof-Carrying Intents — DL+PCI)  
**Rationale:** This system disburses real money without human intervention. It requires absolute auditability and zero-trust mechanisms. Topology C is mandatory.

---

## 1. Business Context

An airline operates an **Autonomous Flight Delay Refund System**. When a flight is delayed beyond a threshold, the system automatically evaluates passenger eligibility and proposes a refund. The payout is executed without human approval, provided the proposal carries a valid cryptographic proof of compliance.

Because real funds are transferred, the system must be:
- **Auditable:** Every decision is recorded in an immutable ledger.
- **Zero-Trust:** The Kernel does not trust the Agent. It verifies proofs.
- **Deterministic at the gate:** Validation is purely algorithmic; no probabilistic reasoning in the execution path.

---

## 2. Trigger

| Field | Value |
|-------|-------|
| **Source** | Airline API (or event bus) |
| **Event** | `FlightDelayEvent` indicating a flight was delayed **more than 3 hours** |
| **Payload** | At minimum: `flight_id`, `scheduled_departure`, `actual_departure`, `delay_minutes`, `affected_passenger_ids` |

The system reacts to this event by initiating a new **DecisionFlow** for each affected passenger (or as a batch, with one DFID per passenger for traceability).

---

## 3. Context Required

The **Context Compiler** (Kernel Space) MUST assemble the following data before invoking the Agent:

| Context Layer | Contents |
|---------------|----------|
| **State (Authoritative)** | Passenger ticket info (PNR, booking class, route, fare), current compensation policy (rules, amounts by delay tier), passenger wallet balance |
| **Session (Ephemeral)** | The `FlightDelayEvent` that triggered the flow |
| **Memory (Historical)** | History of prior decisions and validation rejections for this specific DFID/passenger, preventing decision amnesia and infinite rejection loops |
| **Artifacts (Reference)** | Compensation policy document (EU 261, airline-specific rules), rule-set version hash |

The Agent receives a **Working Context** object. It MUST NOT query external APIs directly. All data comes from the Context Store.

---

## 4. The Agent: Refund Policy Agent (ROA)

The Agent operates strictly under a structured **Responsibility Contract** stored in the Agent Registry. It must implement the formal `ResponsibilityContract` schema (see §6.6). 
For `refund_policy_agent_v1`, the parameters include:
- `owner`: e.g. "compliance@airline.com"
- `version`: "1.0.0"
- `escalate_on_uncertainty`: 0.85 (triggers determinist escalation if confidence falls below this)
- `allowed_policy_types`: `["REFUND_PROPOSAL"]`
- `mission`: "Evaluate passenger eligibility for delay compensation and propose a refund amount consistent with the policy."
- `mission_context_hash`: Cryptographic hash to verify mission integrity
- `output`: A **Proof-Carrying Intent (PCI)**

### 4.1 Agent Responsibilities

1. **Explain:** Interpret the delay event, ticket, and policy. Articulate why the passenger is or is not eligible.
2. **Policy:** Produce a structured intent: `REFUND_PROPOSAL` with `passenger_id`, `amount_eur`, `reason_code`, `policy_ref`.
3. **Self-Check:** Verify the proposal aligns with the agent's mission and boundaries. Escalate if uncertain.
4. **Emit PCI:** Package the intent with a **Proof** (evidence hash) and **Signature** (cryptographic binding to ROA identity).

### 4.2 What the Agent Does NOT Do

- Execute the payout
- Validate its own proposal (that is the Kernel's job)
- Hold API keys or database credentials
- Bypass the Proof Checker

---

## 5. The Architecture: Topology C (DL+PCI)

### 5.1 Mandatory Components

| Component | Location | Responsibility |
|-----------|----------|-----------------|
| **Refund Policy Agent** | User Space | Explain, Policy, emit PCI |
| **Context Compiler** | Kernel Space | Assemble Working Context from Context Store |
| **Proof Checker** | Kernel Space | Verify PCI proofs; reject invalid intents |
| **Decision Ledger** | Kernel Space | Append-only log of verified intents |
| **Execution Engine** | Kernel Space | Trigger payout API only after Ledger commit |

### 5.2 Proof-Carrying Intent (PCI) Structure

The Agent MUST output a `ProofCarryingIntent` with the following structure:

| Field | Type | Description |
|-------|------|-------------|
| `dfid` | UUID | DecisionFlow ID. Immutable trace identifier. |
| `intent_payload` | `RefundProposal` | Structured policy: `passenger_id`, `amount_eur`, `reason_code`, `policy_ref`. |
| `context_ref` | Hash | `ContextSnapshotID` — hash of the Working Context used during reasoning. |
| `evidence_hash` | Hash | `SHA256(DFID ‖ H_state ‖ H_contract ‖ H_rules)`. Proves alignment with state, contract, and rule-set. |
| `roa_signature` | Signature | Cryptographic signature binding the PCI to the Agent's identity (from Agent Registry). |

### 5.3 Evidence Hash Derivation

The `evidence_hash` MUST be computed as:

```
H_evidence = SHA256(DFID || H_state || H_contract || H_rules)
```

Where:
- **H_state:** SHA-256 hash of the Context Snapshot (authoritative state at T_start).
- **H_contract:** SHA-256 hash of the Agent's Responsibility Contract from the Registry.
- **H_rules:** SHA-256 hash of the deterministic validation rules (Hard Gates) applied by the DIM.

### 5.4 Proof Checker Workflow

The Kernel's Proof Checker (DIM) MUST perform, in order:

1. **Identity Attestation:** Verify `roa_signature` against the Agent's public key in the Registry.
2. **Context Binding:** Verify `context_ref` matches the `ContextSnapshotID` from the flow start.
3. **Evidence Hash Validation:** Recompute `H_evidence` using authoritative Registry and Context Store data. Reject if mismatch.
4. **JIT Drift Check:** Verify the live environment state is within the Drift Envelope (e.g., wallet balance unchanged, policy not revoked).
5. **Commit:** If all checks pass, append the PCI to the **Decision Ledger**.
6. **Trigger Execution:** Only after Ledger commit, invoke the Payout API with the validated intent.

### 5.5 Decision Ledger

- **Append-only.** No updates or deletes.
- **Idempotent.** Replaying the same PCI yields the same outcome (or deterministic rejection if state has changed).
- **Immutable.** Every entry is permanently recorded. Auditors verify proofs, not agent reasoning.

### 5.6 Execution Engine

- Receives a **Commit Event** from the Ledger (i.e., a verified PCI).
- Transforms the intent into a **Payout API** call (e.g., credit passenger wallet, or trigger bank transfer).
- Uses **Idempotency Key** = `SHA256(DFID + Step_ID + Canonical_Params)` where `Step_ID = "PAYOUT"` for the payout step.
- Logs the result (transaction ID, status) and associates it with the DFID.

### 5.7 DecisionFlow State Machine

Every DecisionFlow MUST follow this deterministic state machine. The implementation MUST track and persist state transitions.

```
CREATED → ACTIVE (reasoning begins)
ACTIVE  → VALIDATING (PCI submitted to DIM)
VALIDATING → ACCEPTED   (all checks passed)
VALIDATING → ABORTED    (hard rejection — see termination codes)
VALIDATING → ESCALATED  (confidence below threshold, or authority exceeded)
ACCEPTED   → EXECUTING  (Ledger commit triggers payout)
EXECUTING  → CLOSED     (successful execution)
EXECUTING  → ABORTED    (terminal payout failure)
ESCALATED  → ACCEPTED   (human OVERRIDE — approved as-is; no re-validation required)
ESCALATED  → ACTIVE     (human MODIFY — proposal changed; must re-enter full Proof Checker cycle)
ESCALATED  → ABORTED    (human ABORT)
```

**Terminal state reasons (used as `abort_reason` field in flow record):**

| Code | Trigger |
|------|---------|
| `REASONING_EXHAUSTION` | Retry limit (3 per DFID) exceeded without valid PCI |
| `STATE_DRIFT_DETECTED` | JIT re-verification failed; context stale at execution time |
| `MISSION_DISSONANCE` | `mission_context_hash` mismatch — proposal rejected by DIM |
| `RISK_LIMIT_EXCEEDED` | Proposed amount exceeds contract authority ceiling |
| `IDENTITY_ATTESTATION_FAILED` | Invalid `roa_signature` |
| `EVIDENCE_HASH_MISMATCH` | Recomputed `H_evidence` does not match PCI payload |

**DIRTY** is a sub-state of `ABORTED` used only for partial execution failures (e.g., ledger committed but payout API failed terminally). It triggers compensation and prevents re-execution.

---

## 6. Data Models (Minimal)

### 6.1 FlightDelayEvent

```python
# Pydantic model - structure only; implement with full validation
flight_id: str
scheduled_departure: datetime
actual_departure: datetime
delay_minutes: int  # Must be > 180 for trigger
affected_passenger_ids: list[str]
```

### 6.2 RefundProposal (Intent Payload)

```python
passenger_id: str
amount_eur: Decimal  # Non-negative, policy-bounded
reason_code: Literal["EU261_3H", "EU261_4H", "AIRLINE_POLICY", ...]
policy_ref: str  # Version or rule ID
```

### 6.3 ProofCarryingIntent

```python
# Pydantic model — the signed artifact emitted by the Agent to the Kernel
dfid: UUID
intent_payload: RefundProposal
context_ref: str                          # Must equal WorkingContext.context_snapshot_id
evidence_hash: str                        # SHA256(DFID || H_state || H_contract || H_rules)
roa_signature: bytes                      # Ed25519 signature over evidence_hash, keyed to agent's private key
```

### 6.4 CompensationPolicy

```python
# Pydantic model — loaded from Context Store Artifacts layer
policy_id: str
version_hash: str                         # SHA-256 of the canonical policy JSON; used in JIT Drift Check
tiers: list[CompensationTier]             # Ordered list; first matching tier wins
```

```python
# Nested model
class CompensationTier(BaseModel):
    min_delay_minutes: int                # Inclusive lower bound (exclusive upper implied by next tier)
    max_delay_minutes: int | None         # None = no upper bound
    amount_eur: Decimal
    reason_code: str                      # e.g. "EU261_3H", "EU261_4H"
```

### 6.5 DecisionMemoryEntry

```python
# Pydantic model — one entry per prior rejection for this passenger/DFID
dfid: UUID
attempt_number: int
rejection_reason: str                     # e.g. "EVIDENCE_HASH_MISMATCH"
rejection_detail: str                     # Human-readable explanation returned by Proof Checker
timestamp: datetime
```

### 6.6 PassengerTicket

```python
# Pydantic model - structure only; implement with full validation
pnr: str                                  # Booking reference
passenger_id: str
booking_class: Literal["ECONOMY", "BUSINESS", "FIRST"]
route: str                                # e.g. "LHR-JFK"
fare_eur: Decimal
ticket_status: Literal["ACTIVE", "CANCELLED", "USED"]
```

### 6.7 WorkingContext

```python
# Pydantic model — immutable snapshot passed to Agent; MUST NOT be mutated post-assembly
dfid: UUID
context_snapshot_id: str                  # SHA-256 hash — see computation rule below
flight_delay_event: FlightDelayEvent      # Session layer
passenger_ticket: PassengerTicket         # State layer
compensation_policy: CompensationPolicy   # State + Artifacts layer
wallet_balance_eur: Decimal               # State layer
memory: list[DecisionMemoryEntry]         # Memory layer — prior rejections for this passenger
```

**`context_snapshot_id` computation rule:** The Kernel MUST compute this as:
```
context_snapshot_id = SHA256(
    model_dump_json(flight_delay_event)
    + model_dump_json(passenger_ticket)
    + model_dump_json(compensation_policy)
    + str(wallet_balance_eur)
)
```
Fields MUST be serialized with Pydantic `model_dump_json()` in the order listed. The `memory` layer is intentionally excluded from the hash (it is derived state, not authoritative state). The resulting hex string is used as `context_ref` in the PCI.

### 6.8 ResponsibilityContract

```python
# Pydantic model for Agent Registry — registered at deployment, never self-registered
agent_id: str
version: str
owner: str                                # Human accountable for this agent's behavior
role: Literal["EXECUTOR", "STRATEGIST", "MONITOR"]
mission: str
mission_context_hash: str                 # Kernel-computed at deployment; immutable at runtime
allowed_policy_types: list[str]
escalate_on_uncertainty: float            # e.g. 0.85 — deterministic threshold, not a suggestion
aggregate_thresholds: dict[str, float] = {}
public_key: bytes                         # Ed25519 public key; used by Proof Checker to verify roa_signature
```

---

## 7. Failure Modes and Escalation

| Condition | Action |
|-----------|--------|
| Proof verification fails | Reject. Log. Return `ValidationFeedback` (rejection reason) to agent's Memory Context for next cycle. Agent may retry (subject to retry limit). |
| Context drift (e.g., wallet balance changed) | Reject with `STATE_DRIFT_DETECTED`. Recompile fresh `WorkingContext`. Agent may retry (subject to retry limit). |
| Payout API failure (transient) | Retry with exponential backoff. Idempotency key prevents double spend. |
| Payout API failure (terminal) | Mark flow as `DIRTY`. Trigger deterministic compensation from the pre-defined menu (see §7.2). Do NOT ask the Agent to reason about the failure. |
| Agent produces invalid PCI (e.g., bad signature) | Reject. Log. Count toward retry limit. |
| Agent confidence < `escalate_on_uncertainty` | Flow transitioned to `ESCALATED`. Human review required. Human may OVERRIDE, MODIFY, or ABORT. |
| Rejection Loop / Exceeds Escalation Budget | Agent status transitioned to `SUSPENDED` in Agent Registry. Blocks all new and existing DecisionFlows for this agent until human operator intervention. |
| Retry limit exceeded (3 attempts per DFID) | Flow transitioned to `ABORTED` with reason `REASONING_EXHAUSTION`. No further retries. Agent NOT escalated — this is a hard stop. |

### 7.1 Intent Retry Governor

The Kernel MUST enforce a hard retry limit of **3 attempts per DFID**. On every `VALIDATING → ABORTED` transition:

1. The rejection reason is added to the **Memory Context** (ValidationFeedback) for the next cycle.
2. The Kernel increments the attempt counter bound to the DFID.
3. If `attempt_count >= 3`: transition flow to `ABORTED:REASONING_EXHAUSTION` immediately. Do NOT escalate. Do NOT allow further retries.

This prevents context poisoning — an accumulation of contradictory rejections that degrades reasoning quality. The agent corrects via updated Memory Context, not unlimited retries.

### 7.2 Compensation Menu

When a flow reaches a terminal failure state (`DIRTY` or unrecoverable `ABORTED`), the Execution Engine MUST select compensation from the pre-defined menu only:

| Action | When to use |
|--------|-------------|
| `ALERT_HUMAN` | Default for all terminal failures — log and notify operator |
| `REVERT` | Undo a previously committed reversible side effect |
| `CLOSE_ALL` | Emergency shutdown — close all open DecisionFlows for this agent |

**The Agent MUST NOT invent or propose compensation logic.** Compensation is a Kernel responsibility triggered deterministically by flow state.

---

## 8. Out of Scope (For This Sample)

- Full airline API integration (use mocks or stubs).
- Real cryptographic key management (use test keys or in-memory signers).
- Multi-tenant or multi-airline support.
- Human-in-the-loop UI (escalation can be logged only).

---

## 9. Success Criteria

The implementation is complete when:

1. A `FlightDelayEvent` triggers a DecisionFlow.
2. The Context Compiler assembles Working Context from the Context Store.
3. The Refund Policy Agent produces a `ProofCarryingIntent` with valid `evidence_hash` and `roa_signature`.
4. The Proof Checker verifies the PCI and appends it to the Decision Ledger.
5. The Execution Engine triggers the Payout API (or mock) with idempotency.
6. All steps are logged with DFID. No Agent code executes in Kernel Space. No Kernel code calls an LLM.
