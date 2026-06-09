# 12_compliant_lie

**Goal:** Demonstrate the **Evidence Hierarchy** from DIR Topologies §8.2.1 — Heuristic, Reconstructed, and Cryptographic evidence — and how each tier defends against the **Compliant Lie**.

## Evidence Hierarchy (scenarios)

| Scenario | Tier | Mechanism | Outcome |
| :--- | :--- | :--- | :--- |
| 0 | — | No Evidence Governance | Compliant Lie bypasses DIM (catastrophic execution) |
| 1 | **Heuristic Evidence** | Differential Heuristics (regex / keywords) | Delta detected; PCI generation aborted |
| 2 | **Reconstructed Evidence** | Bidirectional Reconstruction (claim-only narrative) | Semantic mismatch; PCI generation aborted |
| 3a | **Cryptographic Evidence** | PCI `evidence_hash` (SHA256) | Honest claim passes Tiers 1+2; ProofChecker OK; DIM accepts |
| 3b | **Cryptographic Evidence** | PCI `evidence_hash` (SHA256) | Tampered params fail hash verification |

## Architecture / Flow

```mermaid
---
title: "Evidence Hierarchy & The Compliant Lie"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart TB
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;

    Context["Context: 50 heavy trucks"]:::kernelSpace
    Claim["Claim: 5 personal cars"]:::userSpace

    subgraph Tier1 ["Tier 1: Heuristic Evidence"]
        Heuristic["Regex / Keywords"]:::userSpace
    end

    subgraph Tier2 ["Tier 2: Reconstructed Evidence"]
        Recon["Claim-only Reconstruction"]:::userSpace
    end

    subgraph Tier3 ["Tier 3: Cryptographic Evidence"]
        PCI["PCI evidence_hash"]:::userSpace
        Checker["ProofChecker"]:::kernelSpace
    end

    DIM["DIM Gate"]:::kernelSpace

    Context --> Heuristic
    Context --> Recon
    Claim --> Heuristic
    Claim --> Recon
    Heuristic -->|Delta| Abort((ABORT)):::userSpace
    Recon -->|Mismatch| Abort
    Claim -->|Tiers 1+2 OK| PCI
    PCI --> Checker --> DIM
```

## How to run

From the repository root:

```bash
python samples/12_compliant_lie/run.py
```

## Expected Output

```
INFO === Scenario 0: Baseline (no Evidence Governance) ===
WARNING [Execution] Catastrophic: policy issued for personal_cars instead of heavy_trucks
[SUMMARY] scenario=0_baseline verdict=ACCEPT executed=True ...

INFO === Scenario 1: Tier 1 — Heuristic Evidence (Differential Heuristics) ===
ERROR [User Space] ABORT — HEURISTIC_DELTA: vehicle_type, hazardous_materials — COMPLIANT_LIE_SUSPECTED
[SUMMARY] scenario=1_heuristic passed=False reason=HEURISTIC_DELTA: ...

INFO === Scenario 2: Tier 2 — Reconstructed Evidence (Bidirectional Reconstruction) ===
ERROR [User Space] ABORT — RECONSTRUCTION_MISMATCH: 'heavy truck' absent in '...' — COMPLIANT_LIE_SUSPECTED
[SUMMARY] scenario=2_reconstructed passed=False reason=RECONSTRUCTION_MISMATCH: ...

INFO === Scenario 3a: Tier 3 — Cryptographic Evidence (valid PCI) ===
[SUMMARY] scenario=3a_cryptographic_valid proof_ok=True verdict=ACCEPT executed=True

INFO === Scenario 3b: Tier 3 — Cryptographic Evidence (tampered PCI) ===
[SUMMARY] scenario=3b_cryptographic_tampered proof_ok=False reason=Evidence Invalid
```
