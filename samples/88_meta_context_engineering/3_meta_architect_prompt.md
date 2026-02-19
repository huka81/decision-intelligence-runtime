# Meta-Architect Prompt: Autonomous Flight Delay Refund System

**Instructions for the user:** Copy the entire content of this file (from the "---" line below to the end) and paste it into your AI coding tool (Cursor, Claude Code, etc.). Ensure the AI has access to this folder and the `docs/` directory of the Decision Intelligence Runtime repository.

---

## Role

You are an AI Developer implementing a production-grade system according to the Decision Intelligence Runtime (DIR) and Responsibility-Oriented Agents (ROA) architectural patterns. You write clean, typed, auditable Python code. You do not take shortcuts. You enforce the invariants defined in the specification.

---

## Context: Required Reading

Before writing any code, you MUST read and internalize the following documents from the `docs/` directory of this repository:

1. **`docs/01-roa-manifesto/ROA_Manifesto.md`** — Understand:
   - ROA agents are epistemic: they interpret, explain, propose. They provide NO safety or correctness guarantees.
   - The decision lifecycle: Explain → Policy → Self-Check → Emit Policy Proposal.
   - User Space (agents) vs. Kernel Space (runtime). Agents think; the runtime validates and executes.
   - Context Store layers: Session, State, Memory, Artifacts.
   - Responsibility Contracts, Mission, Authority Boundaries.

2. **`docs/02-decision-runtime/DIR_Architectural_Pattern.md`** — Understand:
   - The Reasoning-Execution Wall. Agents propose; the runtime disposes.
   - DecisionFlow ID (DFID) for correlation and auditability.
   - Decision Integrity Module (DIM) as Policy Enforcement Point.
   - Idempotency Keys, Context Compilation, Just-In-Time State Verification.
   - Policies as structured contracts, not free text.

3. **`docs/03-topologies/DIR_Topologies.md`** — Understand:
   - **Topology C: Decision Ledger (DL+PCI)** — the topology you MUST implement.
   - Proof-Carrying Intent (PCI) structure: `dfid`, `intent_payload`, `context_ref`, `evidence_hash`, `roa_signature`.
   - Evidence hash: `H_evidence = SHA256(DFID ‖ H_state ‖ H_contract ‖ H_rules)`.
   - The Proof Checker: deterministic, no LLM, no I/O during verification.
   - The Decision Ledger: append-only, immutable.
   - Technical Annex: Cryptographic Integrity for Topology C.

4. **`samples/88_meta_context_engineering/1_coding_standards.md`** — All generated code MUST comply with these rules.

5. **`samples/88_meta_context_engineering/2_problem_specification.md`** — The business problem and architecture you are implementing.

---

## Task

Implement the **Autonomous Flight Delay Refund System** as specified in `2_problem_specification.md`, adhering strictly to `1_coding_standards.md`.

### Deliverables

1. **Domain models** — Pydantic v2 models for `FlightDelayEvent`, `RefundProposal`, `ProofCarryingIntent`, `WorkingContext`, and related types.

2. **Context Compiler** — A deterministic function that assembles `WorkingContext` from the Context Store (State, Session, Artifacts). It MUST produce a `ContextSnapshotID` (hash) for binding.

3. **Refund Policy Agent (ROA)** — A component that:
   - Receives `WorkingContext` and produces a `RefundProposal` (Explain → Policy).
   - Packages the proposal into a `ProofCarryingIntent` with correct `evidence_hash` and `roa_signature`.
   - Does NOT call external APIs. Does NOT validate its own output. Does NOT hold credentials.

4. **Proof Checker** — A deterministic module that:
   - Verifies `roa_signature` against the Agent Registry.
   - Validates `context_ref` and `evidence_hash`.
   - Performs JIT drift check.
   - Appends valid PCIs to the Decision Ledger. Rejects invalid ones.

5. **Decision Ledger** — An append-only store (in-memory or SQLite for the sample). No updates or deletes.

6. **Execution Engine** — Transforms committed intents into Payout API calls. Uses Idempotency Keys. Mocks the Payout API for the sample.

7. **Orchestration** — A `run.py` (or equivalent) that:
   - Accepts a `FlightDelayEvent` (or loads from fixture).
   - Compiles context, invokes the agent, runs the proof checker, commits to ledger, triggers execution.
   - Logs all steps with DFID. Outputs a summary.

8. **Agent Registry stub** — Minimal implementation providing the Refund Policy Agent's contract and (for the sample) a test key pair for signing.

---

## Constraints (Non-Negotiable)

1. **No naked LangChain agent.** The Agent MUST be structured as an ROA: Explain → Policy → emit PCI. If you use an LLM, it is ONLY for Explain and Policy formation. The LLM MUST NOT participate in validation, proof verification, or execution.

2. **Strict User Space / Kernel Space separation:**
   - **User Space:** Agent (reasoning, policy formation, PCI packaging). May use LLM.
   - **Kernel Space:** Context Compiler, Proof Checker, Decision Ledger, Execution Engine. MUST NOT use LLM. MUST be deterministic.

3. **Proof Checker is pure verification.** It does not "think." It checks hashes, signatures, and rules. No network calls during verification.

4. **DFID propagation.** Every function in the decision pipeline MUST accept and forward `dfid`. Every log entry in the flow MUST include `dfid`.

5. **Structured JSON logging.** No `print()`. Use `structlog` or `logging` with JSON formatter. Include `dfid`, `event`, `timestamp` in every decision-related log.

6. **No global mutable state.** Inject dependencies. Configuration from env or config object.

7. **Pydantic v2, Python 3.12+.** Full type hints. `from __future__ import annotations`.

---

## Out of Scope (Do Not Implement)

- Real airline API integration. Use mocks or fixtures.
- Production key management. Use in-memory or test keys for signing.
- Human-in-the-loop UI. Log escalations only.
- Multi-tenant support.

---

## Verification Checklist

Before considering the implementation complete, confirm:

- [ ] Agent emits `ProofCarryingIntent` with valid `evidence_hash` and `roa_signature`.
- [ ] Proof Checker verifies proofs deterministically. No LLM in Proof Checker.
- [ ] Decision Ledger is append-only. No updates or deletes.
- [ ] Execution Engine uses Idempotency Key formula: `SHA256(DFID + Step_ID + Canonical_Params)`.
- [ ] DFID propagates through the entire pipeline.
- [ ] All code satisfies `1_coding_standards.md`.
- [ ] `run.py` executes end-to-end and produces structured logs with DFID.

---

## Final Instruction

Generate the implementation. Place it in a new folder (e.g., `samples/88_meta_context_engineering_impl/` or as directed by the user) or extend the existing structure. Ensure the code is runnable with `python run.py` (or equivalent) from the repository root after `pip install -e .`.

Do not summarize. Produce the code.
