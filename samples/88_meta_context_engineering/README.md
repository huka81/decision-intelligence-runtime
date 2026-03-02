# Meta-Context Engineering: The System Prompt Toolkit

## What This Folder Is

This folder is **not** a Python sample. It contains no executable code. It is a **Meta-Sample**: a proof of the "Context as Code" philosophy that underpins the Decision Intelligence Runtime (DIR) repository.

In the modern AI-driven Software Development Lifecycle (SDLC), **Markdown is the new programming language**. The role of the architect is to define boundaries, rules, and problem specifications in text files. These files act as a **compiler instruction set** for an AI coding agent (Cursor, Claude, or similar) to generate the actual implementation.

## Markdown as a Compiler

Traditional compilers translate source code into machine instructions. Here, the "source code" is a set of Markdown documents:

| Document | Role |
|----------|------|
| `1_coding_standards.md` | **Lexical & semantic rules**: What the generated code must and must not do. |
| `2_problem_specification.md` | **Domain model & requirements**: The business problem to solve. |
| `3_meta_architect_prompt.md` | **Compiler invocation**: The prompt that instructs the AI to produce the implementation. |

The AI agent reads these documents and produces Python code that satisfies all constraints. The architect never writes a single line of implementation; they write specifications. The AI compiles specifications into code.

## How to Use This Sample

1. **Open your AI coding tool** (Cursor, Claude Code, or equivalent) and point it to:
   - This folder (`samples/88_meta_context_engineering/`)
   - The main DIR documentation: [`ROA_Manifesto.md`](../../docs/01-roa-manifesto/ROA_Manifesto.md), [`DIR_Architectural_Pattern.md`](../../docs/02-decision-runtime/DIR_Architectural_Pattern.md), [`DIR_Topologies.md`](../../docs/03-topologies/DIR_Topologies.md)

2. **Copy the contents of `3_meta_architect_prompt.md`** and paste it into a new chat or task.

3. **Submit.** The AI will read the referenced documents and generate a complete, DIR-compliant implementation of the Autonomous Flight Delay Refund System.

4. **Review the output** against `1_coding_standards.md` and `2_problem_specification.md` to verify alignment.

## Why This Matters

- **Auditability:** The specification is version-controlled, human-readable, and traceable. Every design decision is documented before code exists.
- **Reproducibility:** Any AI agent with access to these files can produce a consistent implementation. The "compiler" is deterministic given the same inputs.
- **Separation of Concerns:** Architects specify *what*; AI implements *how*. The boundary is explicit.
- **Zero Trust:** The generated code is validated against the specification. The specification is the source of truth.

## File Inventory

| File | Purpose |
|------|---------|
| `README.md` | This file. Explains the meta-sample concept. |
| `1_coding_standards.md` | Engineering-grade coding rules (Python 3.12+, Pydantic v2, type hints, logging, separation of concerns). |
| `2_problem_specification.md` | Business requirements for the Autonomous Flight Delay Refund System. Mandates Topology C (DL+PCI). |
| `3_meta_architect_prompt.md` | The prompt to paste into your AI coding tool. The "compiler invocation." |

## Relationship to DIR

This meta-sample demonstrates that the DIR architectural philosophy extends beyond runtime code. The same principles: **User Space vs. Kernel Space**, **Proof-Carrying Intents**, **Deterministic Verification** apply to the *process* of building systems. Specification documents are the "Policy Proposals" of the development lifecycle; the AI is the "Prover Agent"; the human architect is the "Proof Checker" who validates the output.

---

*This sample is part of the [Decision Intelligence Runtime](https://github.com/huka81/decision-intelligence-runtime) repository.*
