# Meta-Architect Prompt: Autonomous Flight Delay Refund System

**Instructions for the user:** Copy the entire content of this file (from the "---" line below to the end) and paste it into your AI coding tool (Cursor, Claude Code, etc.). Ensure the AI has access to this folder and the root of the Decision Intelligence Runtime repository.

---

## Role

You are an AI Developer implementing a production-grade system according to the Decision Intelligence Runtime (DIR) and Responsibility-Oriented Agents (ROA) architectural patterns. You write clean, typed, auditable Python code. You do not take shortcuts. You enforce the invariants defined in the specification.

---

## Context: Required Reading (Context Compilation Pattern)

Before writing any code, you MUST read and internalize all documents listed below. They define the "physics" of the system at two distinct layers — neither layer may be skipped.

**Layer 1 — Framework physics (ROA + DIR + Topology C):**

- **`docs/07-dir-minified/DIR-minified.md`** — The single authoritative specification of the Decision Intelligence Runtime. Contains the full ROA manifesto, DIR architectural patterns, all topologies (you MUST implement **Topology C: DL+PCI**), PCI structure, evidence hash formula, DFID semantics, Idempotency Key rules, and all Kernel Space invariants. Read this file completely before reading any domain file.

**Layer 2 — Domain physics (this sample):**

1. **`samples/88_meta_context_engineering/3_threat-model.md`** — Absolute security overrides and adversarial constraints.
2. **`samples/88_meta_context_engineering/2_dir-boundaries.md`** — Architectural and structural invariants for this system.
3. **`samples/88_meta_context_engineering/5_coding-standards.md`** — Implementation patterns and standards.
4. **`samples/88_meta_context_engineering/1_intent.md`** — The business problem, data models, and intent you are implementing.
5. **`samples/88_meta_context_engineering/4_acceptance-criteria.md`** — Deterministic functional verification scenarios.

**CI Enforcement (Hard Layer):** The following YAML files are the deterministic CI gates. Your generated code MUST pass all of them. Read them to understand exactly which import patterns, naming conventions, and structural violations will cause a build failure:
- **`samples/88_meta_context_engineering/semgrep-agent-isolation.yml`** — Enforces Zero Agent I/O (§2.1, SEC-1, DIR-5).
- **`samples/88_meta_context_engineering/semgrep-kernel-determinism.yml`** — Enforces Kernel Space determinism (§2.2, SEC-2, DIR-1).
- **`samples/88_meta_context_engineering/semgrep-security.yml`** — Enforces idempotency key integrity and no global mutable state (SEC-3, SEC-4, DIR-3).

### Conflict Resolution Hierarchy

If generation rules conflict, you MUST apply this strict evaluation hierarchy:
**Threat Model** > **Boundaries** > **Coding Standards** > **Intent + Acceptance Criteria**
*Architectural integrity always supersedes feature delivery.*

---

## Task

Implement the **Autonomous Flight Delay Refund System** as specified in `1_intent.md`, adhering strictly to the constraints in `2_dir-boundaries.md`, `3_threat-model.md`, and `5_coding-standards.md`.

### Deliverables

1. **Domain models** — Pydantic v2 models for `FlightDelayEvent`, `RefundProposal`, `ProofCarryingIntent`, `WorkingContext`, and related types.

2. **Context Compiler** — A deterministic function that assembles `WorkingContext` from the Context Store (State, Session, Memory, Artifacts). It MUST produce a `ContextSnapshotID` (hash) for binding.

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

8. **Agent Registry stub** — Implementation providing the Agent's structured `ResponsibilityContract` (as a Pydantic model), managing the Agent Status (`ACTIVE`, `SUSPENDED`), tracking the Escalation Budget (Circuit Breakers), and providing a test key pair for signing.

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
- [ ] Execution Engine uses Idempotency Key formula: `SHA256(DFID + Step_ID + Canonical_Params)` where `Step_ID = "PAYOUT"`.
- [ ] DFID propagates through the entire pipeline.
- [ ] All code satisfies `5_coding-standards.md`, `3_threat-model.md` and `2_dir-boundaries.md`.
- [ ] Agent Registry tracks Escalation Budget and suspends agent if budget is exceeded.
- [ ] Context Compiler populates the Memory layer of `WorkingContext` with prior rejection history.
- [ ] Intent Retry Governor enforced: max 3 retries per DFID; 4th attempt impossible; flow transitions to `ABORTED:REASONING_EXHAUSTION`.
- [ ] ValidationFeedback: each rejection reason is written to `WorkingContext.memory` before the next agent invocation.
- [ ] Terminal failures use Compensation Menu (`ALERT_HUMAN`, `REVERT`, `CLOSE_ALL`) only — no ad-hoc agent compensation.
- [ ] DecisionFlow state machine implemented: all states (`CREATED`, `ACTIVE`, `VALIDATING`, `ACCEPTED`, `ESCALATED`, `EXECUTING`, `CLOSED`, `ABORTED`, `DIRTY`) are tracked and persisted.
- [ ] `run.py` executes end-to-end and produces structured logs with DFID.
- [ ] `semgrep --config samples/88_meta_context_engineering/semgrep-agent-isolation.yml <impl_dir>` passes with zero errors.
- [ ] `semgrep --config samples/88_meta_context_engineering/semgrep-kernel-determinism.yml <impl_dir>` passes with zero errors.
- [ ] `semgrep --config samples/88_meta_context_engineering/semgrep-security.yml <impl_dir>` passes with zero errors or warnings.

---

## Final Instruction

Generate the implementation. Place it in a new folder (e.g., `samples/88_meta_context_engineering_impl/` or as directed by the user) or extend the existing structure. Ensure the code is runnable with `python run.py` (or equivalent) from the repository root after `pip install -e .`.

Do not summarize. Produce the code.