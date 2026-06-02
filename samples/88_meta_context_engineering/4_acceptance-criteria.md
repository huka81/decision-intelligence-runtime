# Acceptance Tests: Autonomous Flight Delay Refund System

**Document Type:** Compiler Instruction Set — Functional Verification Scenarios  
**Source of Truth:** `1_intent.md`  
**Format:** Gherkin (BDD) — machine-executable contract as described in the *Context as Code* article.  
**Purpose:** Each `Scenario` maps 1:1 to a requirement in `1_intent.md` and MUST be implemented as a deterministic `pytest-bdd` case. No LLM inference. Same input → same output, every time.

**Execution Rule:** `pytest --co -q` MUST discover all scenarios. `pytest` MUST pass with zero failures before implementation is considered complete.

---

## 1. Trigger Verification

> Source: `1_intent.md` §2 (Trigger)

```gherkin
Feature: DecisionFlow Trigger — Flight Delay Event

  Scenario: AT-1 Valid delay triggers DecisionFlow
    Given a FlightDelayEvent with flight_id "LH1234", delay_minutes 200, affected_passenger_ids ["PAX-001"]
    When the event is submitted to the system
    Then a new DecisionFlow is initiated
    And a unique DFID is generated
    And the DFID is a valid UUID v4
    And the flow reaches the Context Compiler

  Scenario: AT-2 Delay below threshold does not trigger
    Given a FlightDelayEvent with flight_id "LH5678", delay_minutes 179, affected_passenger_ids ["PAX-002"]
    When the event is submitted to the system
    Then no DecisionFlow is initiated
    And no DFID is generated
    And the system logs EVENT_BELOW_THRESHOLD
    And no entry exists in the Decision Ledger
    And no payout is issued

  Scenario: AT-3 Boundary — exactly 180 minutes does not trigger
    Given a FlightDelayEvent with flight_id "LH9999", delay_minutes 180, affected_passenger_ids ["PAX-003"]
    When the event is submitted to the system
    Then no DecisionFlow is initiated
    # Trigger condition is delay_minutes > 180, not >=

  Scenario: AT-4 Batch — multiple passengers in one event produce independent flows
    Given a FlightDelayEvent with flight_id "LH1234", delay_minutes 240, affected_passenger_ids ["PAX-010", "PAX-011", "PAX-012"]
    When the event is submitted to the system
    Then three independent DecisionFlows are initiated
    And each flow has a distinct DFID
    And there is no shared state between flows
```

---

## 2. Context Compilation

> Source: `1_intent.md` §3 (Context Required)

```gherkin
Feature: Context Compiler — WorkingContext Assembly

  Background:
    Given the Context Store is seeded with:
      | key                   | value                                  |
      | passenger_ticket      | PNR, booking_class, fare for PAX-001   |
      | compensation_policy   | EU 261 tiers: 3h=250 EUR, 4h=400 EUR   |
      | wallet_balance_eur    | 1000.00                                |

  Scenario: AT-5 WorkingContext is assembled before agent invocation
    Given a FlightDelayEvent for PAX-001 with delay_minutes 240
    And a new DecisionFlow is created with a DFID
    When the Context Compiler runs
    Then a WorkingContext is produced containing all four layers:
      | layer      | field                  |
      | Session    | flight_delay_event     |
      | State      | passenger_ticket       |
      | State      | wallet_balance_eur     |
      | Artifacts  | compensation_policy    |
      | Memory     | memory (list)          |
    And a context_snapshot_id (SHA-256) is computed and attached to the WorkingContext
    And the memory list is empty on the first invocation for this passenger

  Scenario: AT-6 Agent has zero I/O surface
    Given the agent module source code at paths matching **/agent/** or **/user_space/**
    When semgrep analysis runs with config semgrep-agent-isolation.yml
    Then zero findings are reported
    # Forbidden imports: requests, httpx, sqlalchemy, psycopg2, smtplib, aiohttp, urllib
    # Forbidden env access: os.environ, os.getenv
```

---

## 3. Agent Output (Proof-Carrying Intent)

> Source: `1_intent.md` §4 and §5.2

```gherkin
Feature: Refund Policy Agent — Proof-Carrying Intent Emission

  Background:
    Given the compensation policy tiers are: 3–4h = 250 EUR (EU261_3H), >4h = 400 EUR (EU261_4H)

  Scenario: AT-7 Agent produces a valid PCI on happy path
    Given a valid WorkingContext for PAX-001 with delay_minutes 240
    And the EU 261 policy is active
    And the wallet balance is sufficient
    When the Refund Policy Agent processes the WorkingContext
    Then the agent emits a ProofCarryingIntent containing:
      | field          | constraint                               |
      | dfid           | valid UUID v4                            |
      | intent_payload | RefundProposal with passenger_id,        |
      |                | amount_eur, reason_code, policy_ref      |
      | context_ref    | equals WorkingContext.context_snapshot_id|
      | evidence_hash  | valid SHA-256 hex string                 |
      | roa_signature  | valid Ed25519 signature                  |

  Scenario: AT-8 Refund amount matches the correct policy tier
    Given a valid WorkingContext for a passenger with delay_minutes 200
    When the Refund Policy Agent processes the WorkingContext
    Then the ProofCarryingIntent contains amount_eur equal to 250
    And the agent does not propose any amount outside defined policy tiers

  Scenario: AT-9 Reason code is deterministic per delay tier
    Given a valid WorkingContext for a passenger with delay_minutes 200
    When the Refund Policy Agent processes the WorkingContext
    Then the reason_code in the ProofCarryingIntent is "EU261_3H"

    Given a valid WorkingContext for a passenger with delay_minutes 300
    When the Refund Policy Agent processes the WorkingContext
    Then the reason_code in the ProofCarryingIntent is "EU261_4H"
```

---

## 4. Proof Checker (Kernel Validation)

> Source: `1_intent.md` §5.4

```gherkin
Feature: Proof Checker — Deterministic Kernel Validation

  Scenario: AT-10 Valid PCI passes all five verification steps in order
    Given a correctly formed PCI from a registered agent with matching hashes
    When the Proof Checker processes the PCI
    Then Step 1 Identity Attestation passes (roa_signature valid against registry public_key)
    And Step 2 Context Binding passes (context_ref matches context_snapshot_id)
    And Step 3 Evidence Hash recomputation matches the PCI evidence_hash field
    And Step 4 JIT Drift Check passes (state in Context Store unchanged since context_snapshot_id)
    And Step 5 the PCI is appended to the Decision Ledger

  Scenario: AT-11 Proof Checker contains no probabilistic code
    Given the proof checker module source code at paths matching **/proof_checker** or **/kernel/**
    When semgrep analysis runs with config semgrep-kernel-determinism.yml
    Then zero findings are reported
    # Forbidden imports: openai, anthropic, langchain, langchain_core, litellm

  Scenario: AT-12 Corrupted signature is rejected at identity attestation
    Given a PCI where roa_signature has one byte flipped
    When the Proof Checker processes the PCI
    Then the PCI is rejected at Step 1 Identity Attestation
    And the PCI is NOT appended to the Decision Ledger
    And the structured log contains IDENTITY_ATTESTATION_FAILED
    And no payout is issued

  Scenario: AT-13 Stale evidence hash is rejected
    Given a PCI where evidence_hash was computed with an outdated policy version hash
    When the Proof Checker processes the PCI
    Then the PCI is rejected at Step 3 Evidence Hash Validation
    And the structured log contains EVIDENCE_HASH_MISMATCH
    And no payout is issued
```

---

## 5. Decision Ledger

> Source: `1_intent.md` §5.5

```gherkin
Feature: Decision Ledger — Append-Only Audit Store

  Scenario: AT-14 Verified PCI is committed to the Ledger
    Given a PCI that has passed all five Proof Checker steps
    When the Proof Checker commits the PCI
    Then the Ledger contains exactly one new entry for this DFID
    And the entry includes the correct DFID, timestamp, and full PCI payload

  Scenario: AT-15 Ledger exposes no mutating operations
    Given the Decision Ledger implementation
    When its public API is inspected
    Then it exposes no update(), delete(), or remove() methods
    And any attempt to call a mutating operation raises an error or is structurally impossible

  Scenario: AT-16 Duplicate PCI submission is idempotent
    Given a valid PCI that was already committed to the Ledger
    When the same PCI is submitted a second time
    Then the second submission is rejected
    And the Ledger contains exactly one entry for this DFID
```

---

## 6. Execution Engine

> Source: `1_intent.md` §5.6

```gherkin
Feature: Execution Engine — Payout Dispatch with Idempotency

  Scenario: AT-17 Payout fires after Ledger commit
    Given a PCI has been committed to the Decision Ledger for PAX-001 with amount_eur 250
    When the Execution Engine processes the committed intent
    Then the mock Payout API receives exactly one call
    And the call includes passenger_id "PAX-001" and amount_eur 250
    And the Idempotency Key equals SHA256(DFID + "PAYOUT" + canonical_params)

  Scenario: AT-18 No payout occurs for a rejected PCI
    Given a PCI that was rejected by the Proof Checker
    When the pipeline completes
    Then the Execution Engine is not invoked
    And the mock Payout API receives zero calls
```

---

## 7. DFID Propagation and Auditability

> Source: `1_intent.md` §9 (Success Criteria)

```gherkin
Feature: DFID Propagation — End-to-End Correlation

  Scenario: AT-19 DFID is present in every structured log entry
    Given a complete happy-path run for a single FlightDelayEvent
    When all structured log output is captured
    Then every JSON log entry within the DecisionFlow contains the dfid field
    And the dfid value is the correct UUID for this flow

  Scenario: AT-20 Full audit trail is reconstructible from DFID
    Given a single FlightDelayEvent for one passenger has been processed end-to-end
    When an auditor queries all log entries and Ledger records by DFID
    Then the auditor can reconstruct the complete chain in order:
      | step | label                  |
      | 1    | Trigger                |
      | 2    | Context Compilation    |
      | 3    | Agent Explain          |
      | 4    | Agent Policy           |
      | 5    | PCI Emission           |
      | 6    | Proof Verification     |
      | 7    | Ledger Commit          |
      | 8    | Payout Execution       |
    And each step log entry contains the same DFID
```

---

## 8. Failure Modes

> Source: `1_intent.md` §7

```gherkin
Feature: Failure Modes — Deterministic Termination Paths

  Scenario: AT-21 Context drift causes rejection, not payout
    Given a WorkingContext was assembled for PAX-001 with a known context_snapshot_id
    And between Context Compilation and Proof Checking the wallet_balance_eur changes in the Context Store
    When the Proof Checker performs the JIT Drift Check
    Then the PCI is rejected with STATE_DRIFT_DETECTED
    And no entry is added to the Decision Ledger
    And no payout is issued

  Scenario: AT-22 Terminal payout failure marks the flow DIRTY
    Given a PCI has been committed to the Decision Ledger
    And the mock Payout API returns HTTP 500 on every attempt
    When the Execution Engine processes the committed intent
    Then the DecisionFlow state is set to DIRTY
    And the structured log contains ALERT_HUMAN
    And the Agent is NOT invoked to reason about the failure

  Scenario: AT-23 Memory context breaks a rejection loop
    Given a WorkingContext for PAX-001 with an empty memory list
    And the Agent produces a policy proposal that the Proof Checker rejects
    When the rejection reason is written to the Memory layer (ValidationFeedback)
    And the Context Compiler assembles a new WorkingContext for the retry
    Then the new WorkingContext.memory contains the prior rejection reason and detail
    And on retry the Agent reads the rejection from its Memory Context
    And the Agent proposes a different, valid policy

  Scenario: AT-24 Suspended agent is blocked before invocation
    Given the Agent Registry has agent status set to SUSPENDED for refund_policy_agent_v1
    When a new FlightDelayEvent arrives
    Then the DecisionFlow is blocked immediately
    And the Refund Policy Agent is NOT invoked
    And the structured log contains AGENT_SUSPENDED

  Scenario: AT-25 Intent Retry Governor enforces REASONING_EXHAUSTION after 3 rejections
    Given the Proof Checker is configured to reject every PCI for a given DFID
    When the Agent submits a PCI and is rejected for the 1st time
    Then the rejection reason is written to WorkingContext.memory (ValidationFeedback cycle 1)
    When the Agent retries and is rejected for the 2nd time
    Then the rejection reason is written to WorkingContext.memory (ValidationFeedback cycle 2)
    When the Agent retries and is rejected for the 3rd time
    Then the Kernel transitions the flow to ABORTED with abort_reason "REASONING_EXHAUSTION"
    And no 4th invocation of the Agent occurs
    And the flow is NOT escalated to a human operator
    And each of the 3 rejection reasons appears in the corresponding WorkingContext.memory
```

---

## Summary: Requirement Traceability Matrix

| Problem Spec Section    | Scenarios                    | Coverage                                        |
|-------------------------|------------------------------|-------------------------------------------------|
| §2 Trigger              | AT-1, AT-2, AT-3, AT-4       | Threshold, boundary, batch                      |
| §3 Context              | AT-5, AT-6                   | Assembly, isolation                             |
| §4 Agent                | AT-7, AT-8, AT-9             | PCI structure, amounts, reason codes            |
| §5.4 Proof Checker      | AT-10, AT-11, AT-12, AT-13   | Validation pipeline, determinism                |
| §5.5 Ledger             | AT-14, AT-15, AT-16          | Append-only, idempotency                        |
| §5.6 Execution          | AT-17, AT-18                 | Payout dispatch, no-bypass                      |
| §5.7 DecisionFlow States| AT-25                        | Retry governor, REASONING_EXHAUSTION            |
| §7 Failures             | AT-21, AT-22, AT-23, AT-24   | Drift, terminal failure, rejection loops, suspension |
| §9 Auditability         | AT-19, AT-20                 | DFID propagation, full trace                    |
