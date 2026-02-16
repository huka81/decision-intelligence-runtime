# Decision Intelligence Runtime (DIR)

**An architectural framework for building reliable, accountable, and stateful AI decision systems.**

## Project Goal

Current "agent frameworks" treat Large Language Models (LLMs) as autonomous executors, resulting in non-deterministic behaviors, hallucinations in critical control paths, and insufficient accountability mechanisms.

**Decision Intelligence Runtime** addresses this by enforcing a strict separation between **Reasoning** (LLM-based, semantic, probabilistic) and **Execution** (code-based, deterministic, verifiable). This separation is implemented through a Kernel Space / User Space architectural boundary, inspired by operating system design principles.

Unlike purely theoretical frameworks, DIR provides a concrete, executable implementation of safe delegation patterns.

### Origins

DIR emerged from production constraints in the **AIvestor** automated trading system, where the cost of reasoning failures is measured in capital loss. The patterns documented here are not theoretical—they represent battle-tested solutions to "Day Two" failure modes: state drift, non-idempotent operations, TOCTOU vulnerabilities, and the collapse of accountability in multi-agent systems.

This repository contains the architectural concepts, formal specifications, and reference implementations of the DIR framework.

---

## Architectural Convergence & Validation

The publication of *Intelligent AI Delegation* by Google DeepMind (February 2026, arXiv:2602.11865) confirms the architectural direction we have been developing since early 2025. Their formalization of "Responsibility Transfer," "Auditability," and "Permission Handling" as fundamental requirements for agentic systems aligns with the patterns we have been validating in production environments.

The independent convergence is notable:

* **Google's "Responsibility Transfer"** ≈ **ROA Responsibility Contracts**
* **Google's "Auditability"** ≈ **DecisionFlow ID (DFID)**
* **Google's "Permission Handling"** ≈ **Decision Integrity Module (DIM)**

This alignment reinforces that these patterns are not vendor-specific abstractions—they are architectural necessities for production-grade agentic systems.

**[Read the full framework comparison: Google DeepMind vs. DIR/ROA](./docs/00-introduction/Intelligent_Delegation_Framework_Mapping.md)**

---

## Start Here

If you are new to DIR/ROA, begin with the introduction article. It explains the core motivation ("Day Two" failures in production systems), the Kernel Space vs. User Space architectural boundary, and why traditional agentic loops are insufficient for high-stakes environments.

**[Read: Beyond Prompt Engineering — Building a Deterministic Runtime for Responsible AI Agents](./docs/00-introduction/DIR-introduction.md)**

## Core Concepts

### 1. Responsibility-Oriented Agents (ROA)
*Current Status: Published*

ROA is the architectural pattern for agents themselves. Instead of open-ended control loops, ROA constrains agents through explicit contracts:
* **Responsibility Contracts:** Formal scope boundaries and authority limits.
* **Missions:** Explicit optimization objectives defining agent purpose.
* **Stateful Existence:** Long-lived memory and persistent identity.
* **Decision Lifecycle:** Explain → Policy → Proposal (strict separation of reasoning from execution).

**[Read the ROA Manifesto](./docs/01-roa-manifesto/ROA_Manifesto.md)**

### 2. The Runtime Architecture
*Current Status: Published*

The execution environment that enforces deterministic guarantees:
* **Decision Integrity Module (DIM):** Kernel-space validation layer (schema enforcement, RBAC, state consistency checks).
* **Context Compilation:** Immutable state snapshots preventing TOCTOU vulnerabilities.
* **DecisionFlow ID (DFID):** Distributed tracing for reasoning chain reconstruction.
* **Safety Invariants:** Idempotency guarantees, TTL enforcement, and escalation protocols.

**[Read the DIR Architectural Pattern](./docs/02-decision-runtime/DIR_Architectural_Pattern.md)**

### 3. Decision Intelligence Topologies
*Current Status: Work in Progress*

A pluralistic approach to agent orchestration. No single execution model satisfies all operational requirements. DIR defines three distinct topologies optimized for different constraint profiles:
* **Topology A (EOAM):** Event-Oriented Agent Mesh for decentralized strategy coordination.
* **Topology B (SDS):** Structural Decision Streams for high-velocity, grammar-constrained execution.
* **Topology C (DL+PCI):** Decision Ledger with Proof-Carrying Intents for cryptographically verifiable audit trails.

**[Read Decision Intelligence Topologies](./docs/03-topologies/DIR_Topologies.md)**

---

# Getting Started

## Prerequisites
- **Python 3.12+**
- **SQLite3**

## Installation

1. Clone the repository.
2. Install the package in editable mode:

```bash
pip install -e .
```
*This installs the `dir_runtime` package (source in `src/dir_runtime`), making it available to all sample implementations.*

## Repository Structure

```text
decision-intelligence-runtime/
├── src/
│   └── dir_runtime/          # Core framework (Context, DIM, EventBus, etc.)
├── samples/                  # Reference implementations & Topologies
├── docs/                     # Architectural documentation (Specifications)
├── pyproject.toml            # Build configuration
└── README.md                 # This file
```

## Samples & Reference Implementations

Execute any sample from the repository root: `python samples/<folder>/run.py`

### Foundation Patterns

| Sample | Description | Key Concepts |
|--------|-------------|--------------|
| **01_roa_agent** | Basic ROA Agent | Responsibility Contract, Mission, Lifecycle |
| **02_dfid_propagation** | DecisionFlow ID | Distributed Tracing, Correlation |
| **03_idempotency_guard** | Execution Safety | Exact-once execution, Caching |
| **04_context_store** | State Management | Session vs. State vs. Memory layers |
| **05_dim_validation** | Decision Integrity | Schema Validation, RBAC, State Consistency |
| **06_agent_registry** | Discovery | Capability Contracts, Manifests, Priority |

### Topologies

| Sample | Topology | Constraint Profile | Mechanisms |
|--------|----------|-------------------|-------------|
| **09_topology_a_eoam** | **EOAM** (Event-Oriented Agent Mesh) | Complex strategy, multi-agent coordination | Event Bus, Arbitration, Reactive Choreography |
| **10_topology_b_sds** | **SDS** (Structural Decision Stream) | High-velocity, low-latency execution | Grammar Validation, JIT State Drift Detection |
| **11_topology_c_dl_pci** | **DL+PCI** (Decision Ledger + Proof-Carrying Intents) | High-stakes regulatory environments | Immutable Ledger, Cryptographic Intent Proofs |

---
## Documentation

- **[DIR Introduction](./docs/00-introduction/DIR-introduction.md)** - Architectural motivation and Kernel Space / User Space boundary.
- **[ROA Manifesto](./docs/01-roa-manifesto/ROA_Manifesto.md)** - Responsibility-oriented agent design.
- **[DIR Architecture](./docs/02-decision-runtime/DIR_Architectural_Pattern.md)** - Runtime components and invariants.
- **[Topologies](./docs/03-topologies/DIR_Topologies.md)** - Operational modes (EOAM, SDS, DL+PCI).

---

## Author

**Artur Huk** — [LinkedIn](https://www.linkedin.com/in/arturhuk/)

---
*This repository represents an evolving architectural framework derived from production constraints in high-stakes AI decision systems.*