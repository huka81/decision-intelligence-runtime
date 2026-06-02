# Meta-Context Engineering: The System Prompt Toolkit

## What This Folder Is

This folder is **not** a Python sample. It contains no executable code. It is a **Meta-Sample**: a proof of the "Context as Code" philosophy that underpins the Decision Intelligence Runtime (DIR) repository, specifically demonstrating the **Context Compilation Pattern**.

The domain used to illustrate the pattern is an **Autonomous Flight Delay Refund System** — a financial system that disburses real money without human approval, built on **DIR Topology C (Decision Ledger with Proof-Carrying Intents)**. This domain is demanding enough to exercise every layer of the Context Compilation Pattern.

In the modern AI-driven Software Development Lifecycle (SDLC), **Markdown acts as a new programming language**. The role of the engineering team shifts from writing syntax to defining boundaries, rules, and problem specifications in text files. These files act as a **compiler instruction set** for an AI coding agent (Cursor, Claude, or similar) to generate the actual implementation.

## Artifact-Bound Roles

Following the *Context as Code* philosophy, this sample maps directly to specialized engineering roles, where accountability is bound to specific upstream artifacts rather than downstream pull requests:

| File | Type | Associated Role | Purpose |
|------|------|-----------------|---------|
| `1_intent.md` | Soft | **Intent Definer** | Defines the "What" — business context, domain model, Topology C components, DecisionFlow state machine, data models, and failure modes. |
| `2_dir-boundaries.md` | Soft | **World Builder** | Defines the structural gravity — User/Kernel Space partition, I/O isolation invariants, JIT Drift Envelope, and conflict resolution hierarchy. |
| `3_threat-model.md` | Soft | **Adversarial Context Provider** | Defines the negative space — Zero Trust posture, attacker directives (SEC-1–SEC-4), and adversarial QA playbook (5 Traps). |
| `4_acceptance-criteria.md` | Soft | **Intent Definer** | Defines the deterministic proof of delivery — 25 Gherkin acceptance scenarios covering all Topology C components, memory/longevity, and retry governor. |
| `5_coding-standards.md` | Soft | **Context Orchestrator** | Defines lexical and semantic rules — Python 3.12+, Pydantic v2, DIR-specific constraints (DIR-1 through DIR-8). |
| `6_context-compiler-prompt.md` | Soft | **Governance Platform Engineer** | The compiler invocation — orchestrates the context hierarchy, applies conflict resolution, and specifies the full implementation checklist. |
| `context_compiler.py` | **Script** | **Governance Platform Engineer** | The Context Compiler itself — reads all Soft artifacts in authority order and writes `compiled_system_prompt.txt`. Run before invoking any AI agent. |
| `semgrep-agent-isolation.yml` | **Hard** | **Governance Platform Engineer** | CI gate: deterministically enforces Zero Agent I/O (`2_dir-boundaries.md §2.1`, `3_threat-model.md SEC-1`, `DIR-5`). |
| `semgrep-kernel-determinism.yml` | **Hard** | **Governance Platform Engineer** | CI gate: deterministically enforces Kernel Space determinism — no LLM in validation path (`2_dir-boundaries.md §2.2`, `SEC-2`, `DIR-1`). |
| `semgrep-security.yml` | **Hard** | **Governance Platform Engineer** | CI gate: deterministically enforces idempotency key integrity and no global mutable state (`SEC-3`, `SEC-4`, `DIR-3`). |

The AI agent reads the **Soft** documents, resolves any conflicts according to a strict hierarchy (Threat Model > Boundaries > Coding Standards > Intent), and produces Python code that satisfies all constraints. The **Hard** YAML files are then run by the CI pipeline to mechanically verify that the generated code respects every declared boundary — without relying on probabilistic interpretation. The human team never writes implementation; they write specifications and enforcement gates.

## How to Use This Sample

The agent's working context is assembled from **two mandatory layers**. They are not alternatives — both are required:

| Layer | Source | What it provides |
|-------|--------|-----------------|
| **Layer 1 — Framework physics** | [`DIR-minified.md`](../../docs/07-dir-minified/DIR-minified.md) (or the individual `docs/` files) | Domain-agnostic patterns: what ROA, DIR, DIM, DFID, PCI, Topology C *are* |
| **Layer 2 — Domain physics** | This folder (`samples/88_meta_context_engineering/`) | How those patterns apply to *this specific system* — exact drift fields, component names, data models, security traps |

`DIR-minified.md` is an alternative only to the three individual `docs/` files — it is **not** an alternative to this folder's contents.

1. **Compile the context** — run the Context Compiler from the repository root:
   ```bash
   python samples/88_meta_context_engineering/context_compiler.py
   ```
   This produces `compiled_system_prompt.txt` — a single file containing all Soft artifacts concatenated in authority order (Framework physics → Threat Model → Boundaries → Standards → Intent → Acceptance). This is the mundane part: no AI, no vector database, just file concatenation.

2. **Open your AI coding tool** (Cursor, Claude Code, or equivalent) and attach:
   - **Layer 1:** [`DIR-minified.md`](../../docs/07-dir-minified/DIR-minified.md) — framework physics (ROA, DIR, Topology C patterns).  
     *Alternative: the three separate files [`ROA_Manifesto.md`](../../docs/01-roa-manifesto/ROA_Manifesto.md), [`DIR_Architectural_Pattern.md`](../../docs/02-decision-runtime/DIR_Architectural_Pattern.md), [`DIR_Topologies.md`](../../docs/03-topologies/DIR_Topologies.md).*
   - **Layer 2:** The compiled `compiled_system_prompt.txt` (or this folder directly if your tool supports directory context).

3. **Copy the contents of `6_context-compiler-prompt.md`** and paste it into a new chat or task.

4. **Submit.** The AI will read all referenced documents, apply the predefined conflict resolution hierarchy, and generate a complete, DIR-compliant implementation of the Autonomous Flight Delay Refund System based on Topology C.

5. **Review the output** against `4_acceptance-criteria.md` (25 Gherkin scenarios) and `1_intent.md` (DecisionFlow state machine, data models, failure modes) to verify behavioral alignment.

6. **Run the CI gates** against the generated implementation directory:
   ```bash
   semgrep --config samples/88_meta_context_engineering/semgrep-agent-isolation.yml <impl_dir>
   semgrep --config samples/88_meta_context_engineering/semgrep-kernel-determinism.yml <impl_dir>
   semgrep --config samples/88_meta_context_engineering/semgrep-security.yml <impl_dir>
   ```
   Zero errors on all three gates = the structural boundaries have been respected.

## Why This Matters

- **Build-Time Governance:** The architecture is governed *before* the syntax is generated. Conflicting instructions are resolved deterministically by the hierarchy, not by probabilistic model judgment.
- **Hybrid Enforcement:** Every declared boundary exists in two forms — a Markdown constraint for the LLM (soft) and a Semgrep rule for the CI runner (hard). The LLM cannot override the CI gate.
- **Auditability:** The specification is version-controlled, human-readable, and traceable. Every design decision is documented before code exists.
- **Reproducibility:** Any AI agent with access to these files can produce a consistent implementation. The "compiler" is deterministic given the same inputs.
- **Separation of Concerns:** Humans specify *boundaries and intent*; AI implements *syntax*. The boundary is explicit and enforceable.
- **Zero Trust at Generation:** The generated code is treated as an untrusted output — mechanically verified against the specification. The specification is the source of truth.

## Relationship to DIR

This meta-sample demonstrates that the DIR architectural philosophy extends beyond runtime code. The same principles — **User Space vs. Kernel Space**, **Proof-Carrying Intents**, **Deterministic Verification** — apply to the *process* of building systems. Specification documents are the "Policy Proposals" of the development lifecycle; the AI is the "Prover Agent"; the human architect is the "Proof Checker" who validates the output against explicitly declared boundaries.

The context encoded in this sample goes beyond a simple prompt — it includes the complete **DecisionFlow State Machine**, the **Intent Retry Governor** (max 3 retries per DFID, `REASONING_EXHAUSTION`), the **ValidationFeedback** loop (rejections write to Memory Context), the **Compensation Menu** (pre-defined: `ALERT_HUMAN`, `REVERT`, `CLOSE_ALL`), and formal **Pydantic data models** for all domain types. This level of specificity is what separates a context that eliminates guessing from one that merely reduces it.

---

*This sample is part of the [Decision Intelligence Runtime](https://github.com/huka81/decision-intelligence-runtime) repository.*