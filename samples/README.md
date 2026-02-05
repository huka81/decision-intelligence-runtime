# DIR/ROA Samples

Demonstration projects for the Decision Intelligence Runtime (DIR) and Responsibility-Oriented Agents (ROA) architecture.

## MVP (first iteration)

| #   | Sample                  | Description                                      |
|-----|-------------------------|--------------------------------------------------|
| 01  | [01_roa_agent](01_roa_agent/)           | Example ROA agent class: contract, Explain → Policy → Proposal |
| 02  | [02_dfid](02_dfid/)                   | DecisionFlow ID: generation, propagation, logging |
| 07  | [07_event_bus_swappable](07_event_bus_swappable/) | In-memory Event Bus; note on swapping for Kafka/PubSub |
| 08  | [08_bootstrap_sqlite](08_bootstrap_sqlite/)     | Bootstrap: ensure DB and tables exist before run |
| 09  | [09_topology_a_eoam](09_topology_a_eoam/)     | Topology A (EOAM): event mesh, parallel agents, DIM |

Further samples (3-6, 10-13) will be added iteratively after verification of the previous ones.

## Prerequisites

- Python 3.12+
- From repo root: `pip install -e .` or `pip install -r requirements.txt`.
- **Workspace:** `.vscode/settings.json` sets `PYTHONPATH` to `src/` and `python.analysis.extraPaths`, so in Cursor/VS Code the samples run and resolve `dir_runtime` without code in `run.py`. Outside the IDE, set `PYTHONPATH` to the repo `src` directory or use `pip install -e .`.

## Running a sample

From the **repository root**:

```bash
python samples/01_roa_agent/run.py
# or
python samples/02_dfid/run.py
# etc.
```

Each sample has its own `README.md` with goal, how to run, and expected output.
