# Decision Intelligence Runtime (DIR)

**An architectural framework for building reliable, accountable, and stateful AI decision systems.**

## Project Goal
Current "agent frameworks" often treat Large Language Models (LLMs) as autonomous executors, leading to non-deterministic behaviors, hallucinations in critical loops, and a lack of accountability. 

**Decision Intelligence Runtime** is an initiative to separate **Reasoning** (LLM-based, semantic, probabilistic) from **Execution** (Code-based, deterministic, safe).

This repository serves as the home for the architectural concepts, whitepapers, and future reference implementations of this system.

## Start Here

If you're new to DIR/ROA, start with the introduction article that explains the core motivation ("Day Two" failures), and the Kernel Space vs. User Space separation:

**[Read: Beyond Prompt Engineering — Building a Deterministic Runtime for Responsible AI Agents](./docs/00-introduction/DIR-introduction.md)**

## Core Concepts

### 1. Responsibility-Oriented Agents (ROA)
*Current Status: Published*

ROA is the architectural pattern for the agents themselves. Instead of open-ended loops, ROA defines agents by:
* **Responsibility Contracts:** Explicit definitions of scope and authority.
* **Missions:** Clear optimization goals (Why the agent exists).
* **Stateful Existence:** Long-lived memory and identity.
* **Decision Lifecycle:** Explain → Policy → Proposal (Separating reasoning from execution).

**[Read the ROA Manifesto](./docs/01-roa-manifesto/ROA_Manifesto.md)**

### 2. The Runtime Architecture
*Current Status: Published*

The environment where agents live. It handles:
* **Decision Integrity Module (DIM):** Deterministic validation (Schema, RBAC, Risk).
* **Context Compilation:** Providing immutable, relevant state snapshots.
* **DecisionFlow:** Distributed tracing for reasoning chains.
* **Safety Invariants:** Idempotency, TTL, and Escalation protocols.

**[Read the DIR Architectural Pattern](./docs/02-decision-runtime/DIR_Architectural_Pattern.md)**

### 3. Decision Intelligence Topologies
*Current Status: Work in Progress*

A pluralistic approach to agent orchestration. A single "loop" cannot satisfy all requirements, so DIR defines three distinct operational modes:
* **Topology A (EOAM):** Decentralized organizational choreography for complex strategy.
* **Topology B (SDS):** Sovereign streams for high-velocity, constrained execution.
* **Topology C (DL+PCI):** Formal verification where "Proof-Carrying Intents" replace trust.

**[Read Decision Intelligence Topologies](./docs/03-topologies/DIR_Topologies.md)**

## 🛠️ Repository Structure

- `/docs` - Whitepapers, manifestos, and deep-dive conceptual documentation.
- `/assets` - Architecture diagrams and visualizations.
- `/src` - (Upcoming) Reference implementations and code snippets.

## Author

**Artur Huk** [LinkedIn Profile](https://www.linkedin.com/in/arturhuk/)

---
*This repository represents an evolving architectural perspective based on real-world experiments in financial AI systems.*