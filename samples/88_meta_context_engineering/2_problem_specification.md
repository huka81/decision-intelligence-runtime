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
| **Artifacts (Reference)** | Compensation policy document (EU 261, airline-specific rules), rule-set version hash |

The Agent receives a **Working Context** object. It MUST NOT query external APIs directly. All data comes from the Context Store.

---

## 4. The Agent: Refund Policy Agent (ROA)

| Attribute | Value |
|-----------|-------|
| **Agent ID** | `refund_policy_agent_v1` |
| **Role** | Policy formation (Explain → Policy) |
| **Mission** | Evaluate passenger eligibility for delay compensation and propose a refund amount consistent with the policy. |
| **Authority** | May propose `REFUND_PROPOSAL` only. May NOT execute payouts. |
| **Output** | A **Proof-Carrying Intent (PCI)** |

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
- Uses **Idempotency Key** = `SHA256(DFID + "PAYOUT" + canonical_params)` to prevent double payouts.
- Logs the result (transaction ID, status) and associates it with the DFID.

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

As specified in Section 5.2. Must include `dfid`, `intent_payload`, `context_ref`, `evidence_hash`, `roa_signature`.

---

## 7. Failure Modes and Escalation

| Condition | Action |
|-----------|--------|
| Proof verification fails | Reject. Log. Do NOT execute. Do NOT append to Ledger. |
| Context drift (e.g., wallet balance changed) | Reject with `STATE_DRIFT_DETECTED`. Agent may retry with fresh context. |
| Payout API failure (transient) | Retry with exponential backoff. Idempotency key prevents double spend. |
| Payout API failure (terminal) | Mark flow as `DIRTY`. Trigger deterministic compensation (e.g., `ALERT_HUMAN`). Do NOT ask the Agent to "reason" about the failure. |
| Agent produces invalid PCI (e.g., bad signature) | Reject. Log. Abort flow. |

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
