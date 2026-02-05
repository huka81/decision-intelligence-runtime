# 09 - Topology A (Event-Oriented Agent Mesh, EOAM)

**Goal:** Event bus; 2-3 agents subscribe to "Observation"; parallel Policy Proposals; simple arbitration (e.g. priority); DIM; mock execution. All steps logged with DFID.

**ROA/DIR:** DIR Topologies §2 (EOAM: decentralized choreography, parallel reasoning, priority-based preemption).

## How to run

From repo root:

```bash
pip install -e .
python samples/09_topology_a_eoam/run.py
```

## Expected output

- One Observation event triggers multiple agents.
- Each agent produces a Policy Proposal (logged with DFID).
- Runtime selects one (e.g. by priority), DIM validates, mock execution.
- Summary with DFID and chosen proposal.
