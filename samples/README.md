# DIR/ROA Samples

Demonstration projects for the **Decision Intelligence Runtime (DIR)** and **Responsibility-Oriented Agents (ROA)** architecture.

The samples are divided into two categories:
1. **Mechanics & Topologies (Synthetic)**: Focused technical implementations of specific architectural patterns described in the [Manifesto](../docs/01-roa-manifesto/ROA_Manifesto.md) and [DIR Patterns](../docs/02-decision-runtime/DIR_Architectural_Pattern.md).
2. **Business Use Cases**: End-to-end scenarios applying these patterns to real-world-like business problems.

---

## 1. Mechanics & Topologies (Synthetic)
Proste syntetyczne przykłady ilustrujące implementacje poszczególnych mechanizmów.

| # | Sample | Focus | Description |
|---|---|---|---|
| 01 | [01_roa_agent](01_roa_agent/) | [ROA Manifesto](../docs/01-roa-manifesto/ROA_Manifesto.md) | Contract, Explain → Policy → Proposal |
| 02 | [02_dfid_propagation](02_dfid_propagation/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | DecisionFlow ID: generation, propagation, logging |
| 03 | [03_idempotency_guard](03_idempotency_guard/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | Idempotency: preventing duplicate side effects |
| 04 | [04_context_store](04_context_store/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | 4 Layers of Context: Session, State, Memory, Artifacts |
| 05 | [05_dim_validation](05_dim_validation/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | Decision Integrity Module: deterministic validation gate |
| 06 | [06_agent_registry](06_agent_registry/) | [DIR Pattern](../docs/02-decision-runtime/DIR_Architectural_Pattern.md) | Agent Registry: manifests and capability handshake |
| 07 | [07_event_bus_swappable](07_event_bus_swappable/) | Infrastructure | In-memory Event Bus; note on swapping for Kafka/PubSub |
| 08 | [08_bootstrap_sqlite](08_bootstrap_sqlite/) | Infrastructure | Bootstrap: ensure DB and tables exist before run |
| 09 | [09_topology_a_eoam](09_topology_a_eoam/) | [Topologies](../docs/03-topologies/DIR_Topologies.md) | Topology A: Event-Oriented Agent Mesh |
| 10 | [10_topology_b_sds](10_topology_b_sds/) | [Topologies](../docs/03-topologies/DIR_Topologies.md) | Topology B: Sovereign Decision Stream |
| 11 | [11_topology_c_dl_pci](11_topology_c_dl_pci/) | [Topologies](../docs/03-topologies/DIR_Topologies.md) | Topology C: Decision Ledger & Proof-Carrying Intents |

---

## 2. Business Use Cases
Przykłady typu biznesowy use case, łączące mechanizmy w pełne scenariusze.

| # | Sample | Primary Topology | Description |
|---|---|---|---|
| 31 | [31_finance_trading](31_finance_trading/) | [Topology A](../docs/03-topologies/DIR_Topologies.md) | **Finance Trading**: Market quotes, news, parallel agents, dynamic position spawning. |
| 32 | [32_insurance_underwriting](32_insurance_underwriting/) | [Topology C](../docs/03-topologies/DIR_Topologies.md) | **Insurance Underwriting**: Risk evaluation with cryptographic Proof-Carrying Intents (PCI). |
| 33 | [33_fraud_gate](33_fraud_gate/) | [Topology B](../docs/03-topologies/DIR_Topologies.md) | **Real-Time Fraud Gate**: Constrained decoding, JIT state drift, drift-attack demo. |

---

## Prerequisites

- **Python 3.12+**
- **From repo root**: `pip install -e .` or `pip install -r requirements.txt`.
- **Workspace:** `.vscode/settings.json` sets `PYTHONPATH` to `src/` and `python.analysis.extraPaths`, so in Cursor/VS Code the samples run and resolve `dir_runtime` without code in `run.py`. Outside the IDE, set `PYTHONPATH` to the repo `src` directory or use `pip install -e .`.

## Running a sample

From the **repository root**:

```bash
python samples/01_roa_agent/run.py
# or
python samples/31_finance_trading/run.py
```

Each sample has its own `README.md` with goal, how to run, and expected output.
