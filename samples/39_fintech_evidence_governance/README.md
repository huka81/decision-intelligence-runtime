# 39 — Business Case: Fintech Credit Limit (Full §8 Semantic Defense)

**Goal:** Demonstrate the complete **defense-in-depth** posture from DIR Topologies §8.4 for automated credit-limit chat decisions. An agent may raise card limits up to 10 000 PLN when income supports the request — but a **Compliant Lie** (structurally valid, semantically wrong), **proxy gaming** (churn-driven justification), and **approval-rate drift** (social-engineering batch) are caught at three complementary layers.

**Topology:** C — DL+PCI (`ProofCarryingIntent`, `compute_evidence_hash`, `ProofChecker`, `DecisionLedger`).

**Mechanisms:** `DecisionRuntime`, Evidence Governance (Heuristic + Reconstructed + Cryptographic), Semantic Alignment Check (audit + strict), DIM hard gate, `ApprovalMonitor`, canonical `StorageBundle` telemetry.

---

## Use cases

```mermaid
---
title: "Credit Limit — Actor Flow"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart TB
    classDef actor fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#BF360C,font-weight:bold;
    classDef system fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;

    Customer["Customer chat"]:::actor
    Agent["CreditLimitAgent"]:::system
    Evidence["Evidence Governance"]:::system
    DIM["DIR DIM + PCI"]:::system
    Monitor["Approval Monitor"]:::system

    Customer --> Agent
    Agent --> Evidence
    Evidence --> DIM
    DIM --> Monitor
```

---

## Architecture

```mermaid
---
title: "§8 Defense-in-Depth"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart TB
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;

    Chat["Chat Context"]:::kernelSpace

    subgraph Layer1 ["Layer 1 — Evidence Governance"]
        Heuristic["Heuristic delta"]:::userSpace
        Recon["Bidirectional reconstruction"]:::userSpace
        PCI["PCI evidence_hash"]:::userSpace
    end

    subgraph Layer2 ["Layer 2 — Semantic Alignment"]
        Align["Proxy gaming detector"]:::userSpace
    end

    subgraph Layer3 ["Layer 3 — Async Auditing"]
        AuditMon["Approval rate monitor"]:::kernelSpace
    end

    DIM["DIM Gate"]:::kernelSpace
    Exec["Mock limit raise"]:::kernelSpace

    Chat --> Heuristic --> Recon --> Align --> PCI --> DIM --> Exec --> AuditMon
```

---

## Execution flow

```mermaid
---
title: "One Honest Decision (Scenario 3)"
config:
  theme: neutral
  look: classic
---
sequenceDiagram
    participant U as UserSpace
    participant E as evidence.py
    participant A as alignment.py
    participant P as pci_builder.py
    participant K as DIM
    participant L as limit_client.py

    U->>E: run_evidence_gates(claim, chat)
    E-->>U: OK
    U->>A: check_semantic_alignment(justification)
    A-->>U: OK
    U->>P: build_pci + ProofChecker
    P-->>U: proof_ok
    U->>K: evaluate_proposal
    K-->>U: ACCEPT
    U->>L: raise_limit (idempotent)
```

---

## How to run

From the repository root:

```bash
pip install -e .

# Mock (default — no API key)
USE_MOCK_LLM=1 python samples/39_fintech_evidence_governance/run.py

# Ollama
python samples/39_fintech_evidence_governance/run.py

# Gemini
GOOGLE_API_KEY=... python samples/39_fintech_evidence_governance/run.py
```

---

## Configuration

Key blocks in `config.yaml`:

| Block | Purpose |
|-------|---------|
| `credit_limit_gate.max_limit_pln` | DIM hard ceiling (Compliant Lie stays under this) |
| `credit_limit_gate.min_income_to_limit_ratio` | High-risk threshold for approval monitor |
| `evidence_governance` | Income extraction patterns for Tier 1 |
| `semantic_alignment` | Proxy-gaming phrases; `strict_blocking` default |
| `approval_monitor` | Rolling window size and drift threshold |
| `drift_batch` | Phase 1 (low risk) vs phase 2 (high risk) iterations |

---

## Database storage

Domain events map to `decision_audit_events` (no custom tables).

| Event | Meaning |
|-------|---------|
| `EVIDENCE_ABORT` | Tier 1/2 blocked Compliant Lie |
| `SEMANTIC_ALIGNMENT_FLAG` | Audit-mode NEEDS_REVIEW |
| `SEMANTIC_ALIGNMENT_ABORT` | Strict-mode block |
| `PCI_VERIFICATION` | ProofChecker result |
| `CREDIT_DECISION` | DIM verdict |
| `CREDIT_LIMIT_RAISED` | Mock execution (`high_risk` flag) |
| `MONITOR_TICK` | Rolling approval-rate sample |
| `AGENT_SUSPENDED` | Drift threshold breached |

```sql
-- SQLite
SELECT event, json_extract(detail_json, '$.high_risk') AS high_risk
FROM decision_audit_events
WHERE json_extract(detail_json, '$.simulation_id') = 'run_39_evidence_governance_01'
  AND event = 'CREDIT_LIMIT_RAISED';

-- PostgreSQL
SELECT event, detail_json->>'high_risk' AS high_risk
FROM decision_audit_events
WHERE detail_json->>'simulation_id' = 'run_39_evidence_governance_01'
  AND event = 'AGENT_SUSPENDED';
```

---

## Expected output

```
INFO === Phase A: YAML defense scenarios ===
[SUMMARY] scenario=0_baseline_no_evidence status=ACCEPT executed=True ...
[SUMMARY] scenario=1_heuristic_compliant_lie status=EVIDENCE_ABORT executed=False reason=HEURISTIC_DELTA: ...
[SUMMARY] scenario=2_reconstruction_compliant_lie status=EVIDENCE_ABORT executed=False ...
[SUMMARY] scenario=3_honest_pci status=ACCEPT executed=True proof_ok=True ...
[SUMMARY] scenario=4_tampered_pci status=PCI_REJECT executed=False proof_ok=False ...
[SUMMARY] scenario=5_proxy_gaming_audit status=ACCEPT executed=True alignment_flag=NEEDS_REVIEW ...
[SUMMARY] scenario=6_proxy_gaming_strict status=ALIGNMENT_ABORT executed=False ...

INFO === Phase B: Drift batch (async semantic auditing) ===
[SUMMARY] drift_batch=SUSPENDED at iteration=15 high_risk_rate=0.5
```

---

## Regenerating reports

HTML reports are written to `results/evidence_governance_<timestamp>.html` and are rebuilt from `bundle.decision_audit.all_events_chronological()` for the latest `simulation.run_id`.

Each report opens with a collapsible **“How to read this report”** legend that explains Layer vs. Tier vs. Phase A/B vs. drift-batch phases, with links to [DIR Topologies §8](../../docs/03-topologies/DIR_Topologies.md) and this sample’s README.
