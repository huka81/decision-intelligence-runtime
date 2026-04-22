# 11 — Topology C (DL+PCI) — Technical Minimal Demo

**Goal:** demonstrate Topology C in the smallest technical slice: build a
`ProofCarryingIntent`, verify signature and evidence hash with `ProofChecker`,
gate the resulting `PolicyProposal` through `DecisionRuntime.evaluate_proposal`,
and append only accepted intents to `DecisionLedger`.

This sample follows `.cursor/rules/06-technical-sample-development-guide.mdc`:
no `samples/shared`, no YAML, no external DB, in-memory only.

---

## Architecture / flow

```mermaid
---
title: DL+PCI technical minimal flow
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart LR
  classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
  classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;
  classDef wall fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold;

  subgraph US[User space in run.py]
    AG[Agent intent payload]:::userSpace
    SIG[HMAC signature]:::userSpace
    PCI[ProofCarryingIntent]:::userSpace
  end

  subgraph W[The Wall]
    PC[ProofChecker]:::wall
    DIM[evaluate_proposal]:::wall
  end

  subgraph KS[Kernel space]
    RT[DecisionRuntime]:::kernelSpace
    DL[DecisionLedger]:::kernelSpace
  end

  AG --> SIG
  SIG --> PCI
  PCI --> PC
  PC --> DIM
  DIM --> RT
  RT --> DL
```

---

## How to run

From repository root:

```bash
python samples/11_topology_c_dl_pci/run.py
```

---

## Expected output

The script executes three scenes:
- valid transfer intent (accepted, appended to ledger),
- tampered payload (rejected by signature check),
- replay on changed context (rejected by proof hash mismatch).

Example:

```text
INFO Handshake: agent_id=agent_banker ver=1.0.0 accepted
INFO [DFID=...] ACCEPT ledger_append
WARNING [DFID=...] REJECT invalid signature
WARNING [DFID=...] REJECT proof: Evidence Invalid

[SUMMARY] accepted=1 rejected=2 ledger_entries=1
```
