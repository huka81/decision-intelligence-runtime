# DIR/ROA Samples

Demonstration projects for the **Decision Intelligence Runtime (DIR)** and **Responsibility-Oriented Agents (ROA)** architecture.

## Quick Start

The fastest way to see the DIR architecture in action:

```bash
python samples/00_quick_start/run.py
```

This sample demonstrates protection against catastrophic actions (e.g. parsing error 15.500 -> 15,500 ETH) and prompt injection in external data. See [00_quick_start](00_quick_start/README.md).

---

The samples are divided into two categories:
1. **Mechanics & Topologies (Synthetic)**: Focused technical implementations of specific architectural patterns described in the [Manifesto](../docs/01-roa-manifesto/ROA_Manifesto.md) and [DIR Patterns](../docs/02-decision-runtime/DIR_Architectural_Pattern.md).
2. **Business Use Cases**: End-to-end scenarios applying these patterns to real-world-like business problems.

*See also: [Context as Code](../docs/08-conclusion/Context_as_Code.md): the philosophy behind this repository.*

---

## 1. Mechanics & Topologies (Synthetic)
Proste syntetyczne przykłady ilustrujące implementacje poszczególnych mechanizmów.

| # | Sample | Focus | Description |
|---|---|---|---|
| 00 | [00_quick_start](00_quick_start/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | **Quick Start / High-Level Overview**: Full architecture, comma catastrophe, prompt injection |
| 01 | [01_roa_agent](01_roa_agent/) | [ROA Manifesto](../docs/01-roa-manifesto/ROA_Manifesto.md) | Contract, Explain → Policy → Proposal |
| 02 | [02_dfid_propagation](02_dfid_propagation/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | DecisionFlow ID: generation, propagation, logging |
| 03 | [03_idempotency_guard](03_idempotency_guard/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | Idempotency: preventing duplicate side effects |
| 04 | [04_context_store](04_context_store/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | 4 Layers of Context: Session, State, Memory, Artifacts |
| 05 | [05_dim_validation](05_dim_validation/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | Decision Integrity Module: deterministic validation gate |
| 06 | [06_agent_registry](06_agent_registry/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | Agent Registry: contracts and capability handshake |
| 07 | [07_event_bus_swappable](07_event_bus_swappable/) | Infrastructure | In-memory Event Bus; note on swapping for Kafka/PubSub |
| 08 | [08_bootstrap_sqlite](08_bootstrap_sqlite/) | Infrastructure | Bootstrap: ensure DB and tables exist before run |
| 09 | [09_topology_a_eoam](09_topology_a_eoam/) | [Topologies](../docs/03-topologies/DIR_Topologies.md) | Topology A: Event-Oriented Agent Mesh |
| 10 | [10_topology_b_sds](10_topology_b_sds/) | [Topologies](../docs/03-topologies/DIR_Topologies.md) | Topology B: Sovereign Decision Stream |
| 11 | [11_topology_c_dl_pci](11_topology_c_dl_pci/) | [Topologies](../docs/03-topologies/DIR_Topologies.md) | Topology C: Decision Ledger & Proof-Carrying Intents |
| 88 | [88_meta_context_engineering](88_meta_context_engineering/) | [Context as Code](../docs/08-conclusion/Context_as_Code.md), [Topologies](../docs/03-topologies/DIR_Topologies.md) | **Meta-Context Engineering**: System Prompt Toolkit: no executable Python. Markdown as compiler instruction set for AI agents. Paste `3_meta_architect_prompt.md` into Cursor/Claude to generate the Autonomous Flight Delay Refund System (Topology C, DL+PCI). |

---

## 2. Business Use Cases
Przykłady typu biznesowy use case, łączące mechanizmy w pełne scenariusze.

| # | Sample | Primary Topology | Domain | Description |
|---|---|---|---|---|
| 31 | [31_finance_trading](31_finance_trading/) | [Topology A](../docs/03-topologies/DIR_Topologies.md) | Finance/trading | Market quotes, news, parallel agents, dynamic position spawning. |
| 32 | [32_fraud_gate](32_fraud_gate/) | [Topology B](../docs/03-topologies/DIR_Topologies.md) | Fraud detection | Real-time payment fraud gate; constrained decoding, JIT state drift, drift-attack demo. |
| 33 | [33_insurance_underwriting](33_insurance_underwriting/) | [Topology C](../docs/03-topologies/DIR_Topologies.md) | Insurance underwriting | Risk evaluation with cryptographic Proof-Carrying Intents (PCI). |
| 34 | [34_langchain_roa_wrapper](34_langchain_roa_wrapper/) | ROA + DIR | **FinOps** | LangChain ReAct → ROA. Cloud cost management. Verifies mission injection blocks PROD termination. |
| 35 | [35_crewai_roa_wrapper](35_crewai_roa_wrapper/) | ROA + DIR | **Customer claims/refunds** | CrewAI Crew → ROA. E-commerce refunds (EUR). Verifies ACCEPT/ESCALATE/REJECT by category, return window, amount; NL intake. |

---

## Prerequisites

- **Python 3.12+**
- **From repo root**: `pip install -e .` or `pip install -r requirements.txt`.
- **Workspace:** `.vscode/settings.json` sets `PYTHONPATH` to `src/` and `python.analysis.extraPaths`, so in Cursor/VS Code the samples run and resolve `dir` without code in `run.py`. Outside the IDE, set `PYTHONPATH` to the repo `src` directory or use `pip install -e .`.

## Running a sample

From the **repository root**:

```bash
python samples/00_quick_start/run.py   # Quick Start (recommended)
# or
python samples/01_roa_agent/run.py
# or
python samples/31_finance_trading/run.py
```

Each sample has its own `README.md` with goal, how to run, and expected output.
