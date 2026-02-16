# Decision Intelligence Runtime (DIR)

**An architectural framework for building reliable, accountable, and stateful AI decision systems.**

## Project Goal
Current "agent frameworks" often treat Large Language Models (LLMs) as autonomous executors, leading to non-deterministic behaviors, hallucinations in critical loops, and a lack of accountability. 

**Decision Intelligence Runtime** is an initiative to separate **Reasoning** (LLM-based, semantic, probabilistic) from **Execution** (Code-based, deterministic, safe).

This repository serves as the home for the architectural concepts, whitepapers, and future reference implementations of this system.

---

### DIR/ROA: The Implementation Layer for Intelligent AI Delegation

On February 12, 2026, Google DeepMind published *Intelligent AI Delegation* (arXiv:2602.11865). Their theoretical findings on "Responsibility Transfer" and "Adaptive Coordination" converge remarkably with the architectural patterns validated in this repository since 2025.

We have mapped the two frameworks to show how **Decision Intelligence Runtime (DIR)** provides the production-ready implementation of Google's theoretical concepts:

* **Google's "Responsibility Transfer"** ➔ **ROA Responsibility Contracts**
* **Google's "Auditability"** ➔ **DecisionFlow ID (DFID)**
* **Google's "Permission Handling"** ➔ **Kernel Space / DIM**

**[Read the full framework mapping: Google DeepMind vs. DIR/ROA](./docs/00-introduction/Intelligent_Delegation_Framework_Mapping.md)**

---

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

---

# 🚀 Getting Started / Jak pracować z repozytorium

## Prerequisites
- **Python 3.12+**
- **SQLite3**

## Installation

1. Clone the repository.
2. Install the package in editable mode:

```bash
pip install -e .
```
*This installs the `dir_runtime` package (source in `src/dir_runtime`), making it available to all samples.*

## 📂 Repository Structure

```text
decision-intelligence-runtime/
├── src/
│   └── dir_runtime/          # Core framework (Context, DIM, EventBus, etc.)
├── samples/                  # Reference implementations & Topologies
├── docs/                     # Architectural documentation (Whitepapers)
├── pyproject.toml            # Build configuration
└── README.md                 # This file
```

## 🧪 Samples & Tutorials

Run any sample using `python samples/<folder>/run.py`. Ensure you are in the repository root.

### Core Concepts

| Sample | Description | Key Concepts |
|--------|-------------|--------------|
| **01_roa_agent** | Basic ROA Agent | Responsibility Contract, Mission, Lifecycle |
| **02_dfid_propagation** | DecisionFlow ID | Distributed Tracing, Correlation |
| **03_idempotency_guard** | Execution Safety | Exact-once execution, Caching |
| **04_context_store** | State Management | Session vs. State vs. Memory layers |
| **05_dim_validation** | Decision Integrity | Schema Validation, RBAC, State Consistency |
| **06_agent_registry** | Discovery | Capability Contracts, Manifests, Priority |

### Advanced Topologies

| Sample | Topology | Use Case | Features |
|--------|----------|----------|----------|
| **09_topology_a_eoam** | **EOAM** (Event-Oriented Agent Mesh) | Complex Strategy, Multi-Agent | Event Bus, Arbitration, Reactive Agents |
| **10_topology_b_sds** | **SDS** (Structural Decision Stream) | High-Velocity / Trading | Grammar Validation, JIT Drift Check, Batching |
| **11_topology_c_dl_pci** | **DL+PCI** (Ledger & Proofs) | High-Stakes / Banking | Immutable Ledger, Cryptographic Proofs (PCI) |

---
## 📚 Documentation

- **[DIR Introduction](./docs/00-introduction/DIR-introduction.md)** - Why we need a runtime.
- **[ROA Manifesto](./docs/01-roa-manifesto/ROA_Manifesto.md)** - Agent architecture.
- **[DIR Architecture](./docs/02-decision-runtime/DIR_Architectural_Pattern.md)** - Runtime components.
- **[Topologies](./docs/03-topologies/DIR_Topologies.md)** - Operational modes (EOAM, SDS, DL+PCI).

---

## Author

**Artur Huk** [LinkedIn Profile](https://www.linkedin.com/in/arturhuk/)

---
*This repository represents an evolving architectural perspective based on real-world experiments in financial AI systems.*