# Decision Intelligence Runtime (DIR)

**An architectural framework for building reliable, accountable, and stateful AI decision systems.**

![Responsibility-Oriented Agents](./assets/images/2_dir_roa_scratch.png)

## Project Goal

Current "agent frameworks" treat Large Language Models (LLMs) as autonomous executors, resulting in non-deterministic behaviors, hallucinations in critical control paths, and insufficient accountability mechanisms.

**Decision Intelligence Runtime** addresses this by enforcing a strict separation between **Reasoning** (LLM-based, semantic, probabilistic) and **Execution** (code-based, deterministic, verifiable). This separation is implemented through a Kernel Space / User Space architectural boundary, inspired by operating system design principles.

Unlike purely theoretical frameworks, DIR provides a concrete, executable implementation of safe delegation patterns.

### Origins

DIR emerged from production constraints in the **AIvestor** automated trading system, where the cost of reasoning failures is measured in capital loss. The patterns documented here are not theoretical-they represent battle-tested solutions to "Day Two" failure modes: state drift, non-idempotent operations, TOCTOU vulnerabilities, and the collapse of accountability in multi-agent systems.

This repository contains the architectural concepts, formal specifications, and reference implementations of the DIR framework.

---

## Architectural Convergence & Validation

The publication of *Intelligent AI Delegation* by Google DeepMind (February 2026, arXiv:2602.11865) confirms the architectural direction we have been developing since early 2025. Their formalization of "Responsibility Transfer," "Auditability," and "Permission Handling" as fundamental requirements for agentic systems aligns with the patterns we have been validating in production environments.

The independent convergence is notable:

* **Google's "Responsibility Transfer"** ≈ **ROA Responsibility Contracts**
* **Google's "Auditability"** ≈ **DecisionFlow ID (DFID)**
* **Google's "Permission Handling"** ≈ **Decision Integrity Module (DIM)**

This alignment reinforces that these patterns are not vendor-specific abstractions-they are architectural necessities for production-grade agentic systems.

### Industry Validation: Google DeepMind vs. DIR Implementation

While Google's *Intelligent AI Delegation* (2026) outlines the *theoretical* requirements for safe agentic systems, **DIR provides the open-source architectural implementation available today.**

| Requirement (Google DeepMind) | DIR Implementation (This Repo) | Status |
| :--- | :--- | :--- |
| **Verifiable Task Completion** | **Topology C (DL+PCI)** <br> *Cryptographic Proof-Carrying Intents* | ✅ Implemented |
| **Transfer of Authority** | **Responsibility Contracts** <br> *Machine-readable scope definitions* | ✅ Implemented |
| **Permission Handling** | **Kernel Space (DIM)** <br> *Deterministic policy enforcement* | ✅ Implemented |
| **Structural Transparency** | **DecisionFlow ID (DFID)** <br> *End-to-end distributed tracing* | ✅ Implemented |


**[Read the full framework comparison: Google DeepMind vs. DIR/ROA](./docs/00-introduction/Intelligent_Delegation_Framework_Mapping.md)**

---

## Start Here

If you are new to DIR/ROA, begin with the introduction article. It explains the core motivation ("Day Two" failures in production systems), the Kernel Space vs. User Space architectural boundary, and why traditional agentic loops are insufficient for high-stakes environments.

**[Read: Beyond Prompt Engineering - Building a Deterministic Runtime for Responsible AI Agents](./docs/00-introduction/DIR-introduction.md)**

## Why use DIR today?

Big Tech providers are beginning to theorize about "Agent Runtimes" as proprietary cloud services. **DIR is the first open-source implementation of the Zero Trust Agents philosophy** - agents propose, the runtime verifies; no implicit trust in LLM output.

* **No Vendor Lock-in:** Run your agents on AWS, Azure, GCP, or on-premise. The runtime logic is yours.
* **Ready for Production:** Solves "Day Two" problems (loops, drifts, audit) that simple orchestration libraries ignore.
* **Works with Existing Frameworks:** DIR is not a competitor to LangChain, AutoGen, or LangGraph - it's the execution shell. Wrap task-oriented agents in ROA contracts, inject mission boundaries, and enforce deterministic validation. *(See: [34_langchain_roa_wrapper](samples/34_langchain_roa_wrapper/), [35_crewai_roa_wrapper](samples/35_crewai_roa_wrapper/))*
* **Language Agnostic Architecture:** While the reference implementation is Python, the patterns (Kernel/User separation, DFID) are universal.
* **Context as Code:** Documentation is the new compiler - Markdown files act as system prompts for AI agents. *([Context as Code](./docs/08-conclusion/Context_as_Code.md))*

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
- **SQLite3** (optional - only for samples that use persistent storage)
- **Ollama** (optional - for local LLM inference in samples such as `31_finance_trading`; use `USE_MOCK_LLM=1` to run without it)

## Installation

1. Clone the repository.
2. Install the package in editable mode:

```bash
pip install -e .
```
*This installs the `dir` package (source in `src/dir`), making it available to all sample implementations.*

## Repository Structure

```text
decision-intelligence-runtime/
├── README.md
├── pyproject.toml            # pip install -e . installs dir
├── requirements.txt          # Shared dependencies
├── src/
│   └── dir/          # Core framework (DFID, DIM, EventBus, Context, etc.)
├── samples/                  # Reference implementations (01–11 mechanics, 31+ use cases)
│   ├── README.md             # Sample catalog and run instructions
│   ├── 01_roa_agent/ … 11_topology_c_dl_pci/
│   ├── 31_finance_trading/ … 35_crewai_roa_wrapper/
│   └── 88_meta_context_engineering/   # Meta-sample: System Prompt Toolkit
├── docs/                     # Architectural documentation
│   ├── 00-introduction/      # DIR intro, framework mapping
│   ├── 01-roa-manifesto/
│   ├── 02-decision-runtime/
│   ├── 03-topologies/
│   └── 08-conclusion/        # Context as Code concept
└── assets/                   # Images, diagrams
```

## Samples & Reference Implementations

Execute any sample from the repository root: `python samples/<folder>/run.py`

*Full list and details: [samples/README.md](samples/README.md)*

### Mechanics & Topologies (01–11)

| # | Sample | Focus | Description |
|---|--------|-------|--------------|
| 01 | `01_roa_agent` | ROA Manifesto | Contract, Explain → Policy → Proposal |
| 02 | `02_dfid_propagation` | DIR Pattern | DecisionFlow ID: generation, propagation, logging |
| 03 | `03_idempotency_guard` | DIR Pattern | Idempotency: preventing duplicate side effects |
| 04 | `04_context_store` | DIR Pattern | 4 Layers of Context: Session, State, Memory, Artifacts |
| 05 | `05_dim_validation` | DIR Pattern | Decision Integrity Module: deterministic validation gate |
| 06 | `06_agent_registry` | DIR Pattern | Agent Registry: manifests and capability handshake |
| 07 | `07_event_bus_swappable` | Infrastructure | In-memory Event Bus; note on swapping for Kafka/PubSub |
| 08 | `08_bootstrap_sqlite` | Infrastructure | Bootstrap: ensure DB and tables exist before run |
| 09 | `09_topology_a_eoam` | Topology A | Event-Oriented Agent Mesh |
| 10 | `10_topology_b_sds` | Topology B | Sovereign Decision Stream |
| 11 | `11_topology_c_dl_pci` | Topology C | Decision Ledger & Proof-Carrying Intents |
| 88 | `88_meta_context_engineering` | Meta-Sample | **Travel/insurance**: System Prompt Toolkit. Domain: flight delay refunds. Generates Flight Delay Refund System (Topology C). |

### Business Use Cases (31+)

| # | Sample | Topology | Domain | What it checks |
|---|--------|----------|--------|----------------|
| 31 | `31_finance_trading` | EOAM | **Finance/trading** | Market quotes, news, parallel agents; position spawning and execution. |
| 32 | `32_fraud_gate` | SDS | **Fraud detection** | Real-time payment fraud gate; constrained decoding, JIT state drift, drift-attack demo. |
| 33 | `33_insurance_underwriting` | DL+PCI | **Insurance underwriting** | Risk evaluation with cryptographic Proof-Carrying Intents (PCI). |
| 34 | `34_langchain_roa_wrapper` | ROA + DIR | **FinOps** | LangChain ReAct → ROA. Cloud cost management. Verifies mission injection blocks PROD termination. |
| 35 | `35_crewai_roa_wrapper` | ROA + DIR | **Customer claims/refunds** | CrewAI Crew → ROA. E-commerce refunds (EUR). Verifies ACCEPT/ESCALATE/REJECT by category, return window, amount; NL intake. |

---
## Documentation

- **[DIR Introduction](./docs/00-introduction/DIR-introduction.md)** - Architectural motivation and Kernel Space / User Space boundary.
- **[ROA Manifesto](./docs/01-roa-manifesto/ROA_Manifesto.md)** - Responsibility-oriented agent design.
- **[DIR Architecture](./docs/02-decision-runtime/DIR_Architectural_Pattern.md)** - Runtime components and invariants.
- **[Topologies](./docs/03-topologies/DIR_Topologies.md)** - Operational modes (EOAM, SDS, DL+PCI).
- **[Context as Code](./docs/08-conclusion/Context_as_Code.md)** - Treating documentation as a system prompt.

---

## Author

**Artur Huk** - [LinkedIn](https://www.linkedin.com/in/arturhuk/)

---
*This repository represents an evolving architectural framework derived from production constraints in high-stakes AI decision systems.*