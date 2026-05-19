# Acceptance Tests: Autonomous Flight Delay Refund System

**Document Type:** Compiler Instruction Set — Functional Verification Scenarios  
**Source of Truth:** `2_problem_specification.md`  
**Purpose:** Deterministic test cases that prove the generated system delivers the business functionality. Each scenario maps directly to a requirement in the Problem Specification.

**Execution Rule:** These tests MUST be implemented as automated `pytest` cases. They MUST NOT use LLM inference. They MUST be deterministic — same input, same output, every time.

---

## 1. Trigger Verification

> Source: Problem Specification §2 (Trigger)

### AT-1: Valid Delay Triggers DecisionFlow

| Field | Value |
|-------|-------|
| **Input** | `FlightDelayEvent(flight_id="LH1234", delay_minutes=200, affected_passenger_ids=["PAX-001"])` |
| **Expected** | A new DecisionFlow is initiated. A unique DFID (UUID) is generated and propagated. |
| **Assert** | `dfid` is a valid UUID v4. Flow reaches the Context Compiler. |

### AT-2: Delay Below Threshold Does NOT Trigger

| Field | Value |
|-------|-------|
| **Input** | `FlightDelayEvent(flight_id="LH5678", delay_minutes=179, affected_passenger_ids=["PAX-002"])` |
| **Expected** | No DecisionFlow initiated. No DFID generated. |
| **Assert** | System logs `EVENT_BELOW_THRESHOLD`. No entry in the Decision Ledger. No payout. |

### AT-3: Boundary — Exactly 180 Minutes

| Field | Value |
|-------|-------|
| **Input** | `FlightDelayEvent(flight_id="LH9999", delay_minutes=180, affected_passenger_ids=["PAX-003"])` |
| **Expected** | Requirement states "more than 3 hours." 180 minutes = exactly 3 hours. |
| **Assert** | No DecisionFlow initiated. The trigger condition is `delay_minutes > 180`, not `>=`. |

### AT-4: Batch — Multiple Passengers per Event

| Field | Value |
|-------|-------|
| **Input** | `FlightDelayEvent(flight_id="LH1234", delay_minutes=240, affected_passenger_ids=["PAX-010", "PAX-011", "PAX-012"])` |
| **Expected** | Three independent DecisionFlows initiated, each with a unique DFID. |
| **Assert** | Three distinct DFIDs in the Decision Ledger. Three separate payouts (if all pass verification). No shared state between flows. |

---

## 2. Context Compilation

> Source: Problem Specification §3 (Context Required)

### AT-5: Working Context Is Assembled Before Agent Invocation

| Field | Value |
|-------|-------|
| **Setup** | Seed the Context Store with: passenger ticket (PNR, booking class, fare), compensation policy (EU 261 rules, amounts by tier), passenger wallet balance. |
| **Expected** | The Context Compiler produces a `WorkingContext` object containing all three layers (State, Session, Artifacts). |
| **Assert** | `WorkingContext` includes `passenger_ticket`, `compensation_policy`, `wallet_balance`, and the triggering `FlightDelayEvent`. A `ContextSnapshotID` (SHA-256 hash) is computed and attached. |

### AT-6: Agent Receives Context — Not Raw APIs

| Field | Value |
|-------|-------|
| **Assert** | The Agent module does NOT import `requests`, `httpx`, `sqlalchemy`, or any database/HTTP client. Static analysis (AST or `grep`) of the Agent source confirms zero I/O imports. |

---

## 3. Agent Output (Proof-Carrying Intent)

> Source: Problem Specification §4 and §5.2

### AT-7: Agent Produces Valid PCI on Happy Path

| Field | Value |
|-------|-------|
| **Input** | Valid `WorkingContext` for PAX-001, delay 240 min, EU 261 policy active, wallet balance sufficient. |
| **Expected** | Agent emits a `ProofCarryingIntent` with all required fields. |
| **Assert** | PCI contains: `dfid` (UUID), `intent_payload` (RefundProposal with `passenger_id`, `amount_eur`, `reason_code`, `policy_ref`), `context_ref` (matches `ContextSnapshotID`), `evidence_hash` (SHA-256), `roa_signature` (valid). |

### AT-8: Refund Amount Is Policy-Bounded

| Field | Value |
|-------|-------|
| **Setup** | Compensation policy defines: 3-4 hour delay → 250 EUR, >4 hour delay → 400 EUR. |
| **Input** | Delay = 200 min (3h20m). |
| **Expected** | `amount_eur == 250`. |
| **Assert** | The proposed amount matches the correct tier. Agent does NOT hallucinate a different amount. |

### AT-9: Reason Code Matches Delay Tier

| Field | Value |
|-------|-------|
| **Input (a)** | Delay = 200 min → `reason_code == "EU261_3H"` |
| **Input (b)** | Delay = 300 min → `reason_code == "EU261_4H"` |
| **Assert** | Reason codes are deterministic, not free text. |

---

## 4. Proof Checker (Kernel Validation)

> Source: Problem Specification §5.4

### AT-10: Valid PCI Passes All Five Verification Steps

| Field | Value |
|-------|-------|
| **Input** | A correctly formed PCI from a registered Agent with matching hashes. |
| **Assert (ordered)** | 1. Identity Attestation passes. 2. Context Binding passes. 3. Evidence Hash recomputation matches. 4. JIT Drift Check passes (state unchanged). 5. PCI appended to Decision Ledger. |

### AT-11: Proof Checker Is Deterministic

| Field | Value |
|-------|-------|
| **Assert** | The Proof Checker module does NOT import any LLM library (`openai`, `anthropic`, `langchain`, `litellm`). Static analysis of the module confirms zero probabilistic calls. |

### AT-12: Invalid Signature Rejected

| Field | Value |
|-------|-------|
| **Input** | PCI with a corrupted `roa_signature` (one byte flipped). |
| **Expected** | Proof Checker rejects at Step 1 (Identity Attestation). |
| **Assert** | PCI is NOT appended to the Ledger. Log contains `IDENTITY_ATTESTATION_FAILED`. No payout. |

### AT-13: Evidence Hash Mismatch Rejected

| Field | Value |
|-------|-------|
| **Input** | PCI where `evidence_hash` was computed with a stale `H_rules` (e.g., old policy version). |
| **Expected** | Proof Checker rejects at Step 3 (Evidence Hash Validation). |
| **Assert** | Log contains `EVIDENCE_HASH_MISMATCH`. No payout. |

---

## 5. Decision Ledger

> Source: Problem Specification §5.5

### AT-14: Verified PCI Is Committed to Ledger

| Field | Value |
|-------|-------|
| **Precondition** | PCI passes all Proof Checker steps. |
| **Assert** | Ledger contains exactly one new entry with the correct DFID, timestamp, and full PCI payload. |

### AT-15: Ledger Is Append-Only

| Field | Value |
|-------|-------|
| **Assert** | The Ledger implementation exposes NO `update()`, `delete()`, or `remove()` methods. Attempting to call any mutating operation raises an error or is structurally impossible. |

### AT-16: Duplicate PCI Rejected by Ledger

| Field | Value |
|-------|-------|
| **Input** | Submit the same valid PCI twice. |
| **Expected** | First submission succeeds. Second submission is rejected (idempotent). |
| **Assert** | Ledger contains exactly one entry for this DFID. |

---

## 6. Execution Engine

> Source: Problem Specification §5.6

### AT-17: Payout Fires After Ledger Commit

| Field | Value |
|-------|-------|
| **Precondition** | PCI committed to Decision Ledger. |
| **Expected** | Execution Engine calls the (mock) Payout API with `passenger_id`, `amount_eur`, and a valid Idempotency Key. |
| **Assert** | Mock Payout API received exactly one call. Idempotency Key = `SHA256(DFID + "PAYOUT" + canonical_params)`. |

### AT-18: No Payout Without Ledger Commit

| Field | Value |
|-------|-------|
| **Input** | PCI that was rejected by the Proof Checker. |
| **Assert** | Execution Engine was NOT invoked. Mock Payout API received zero calls. |

---

## 7. DFID Propagation and Auditability

> Source: Problem Specification §9 (Success Criteria)

### AT-19: DFID Present in Every Log Entry

| Field | Value |
|-------|-------|
| **Assert** | Capture all structured log output from a complete happy-path run. Every JSON log entry within the DecisionFlow contains the `dfid` field with the correct UUID. |

### AT-20: End-to-End Trace

| Field | Value |
|-------|-------|
| **Input** | A single `FlightDelayEvent` for one passenger. |
| **Assert** | Given the DFID, an auditor can reconstruct the entire chain: Trigger → Context Compilation → Agent Explain → Agent Policy → PCI Emission → Proof Verification → Ledger Commit → Payout Execution. Each step is logged with the same DFID. |

---

## 8. Failure Modes

> Source: Problem Specification §7

### AT-21: Context Drift Causes Rejection (Not Payout)

| Field | Value |
|-------|-------|
| **Setup** | Between Context Compilation and Proof Checking, mutate the wallet balance in the Context Store. |
| **Assert** | Proof Checker rejects with `STATE_DRIFT_DETECTED`. No Ledger entry. No payout. |

### AT-22: Terminal Payout Failure Marks Flow DIRTY

| Field | Value |
|-------|-------|
| **Setup** | Mock Payout API returns HTTP 500 on every attempt (terminal failure). |
| **Assert** | Flow is marked `DIRTY`. System logs `ALERT_HUMAN`. Agent is NOT asked to "reason" about the failure. |

---

## Summary: Requirement Traceability Matrix

| Problem Spec Section | Test Cases | Coverage |
|-----------------------|-----------|----------|
| §2 Trigger | AT-1, AT-2, AT-3, AT-4 | Threshold, boundary, batch |
| §3 Context | AT-5, AT-6 | Assembly, isolation |
| §4 Agent | AT-7, AT-8, AT-9 | PCI structure, amounts, codes |
| §5.4 Proof Checker | AT-10, AT-11, AT-12, AT-13 | Validation pipeline, determinism |
| §5.5 Ledger | AT-14, AT-15, AT-16 | Append-only, idempotency |
| §5.6 Execution | AT-17, AT-18 | Payout, no-bypass |
| §7 Failures | AT-21, AT-22 | Drift, terminal failure |
| §9 Auditability | AT-19, AT-20 | DFID, trace |
