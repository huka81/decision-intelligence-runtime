# 33 - Business Case: Insurance Underwriting (Topology C)

**Goal:** Demonstrate the **Digital Underwriter** use case with a **full ROA agent** (Explain → Policy → Self-Check) backed by LLM. Config-driven via `config.yaml` (same convention as samples 31, 32, 35). The system commits to the Decision Ledger only when the agent provides a valid cryptographic **Evidence Hash** proving compliance with the Responsibility Contract.

**Day Two prevention:** Unverified agent decisions (hallucinations, rule violations, forged proofs) never become binding contracts. The DIM (Proof Checker) recalculates the Evidence Hash using authoritative sources and rejects any mismatch (Zero Trust).

**ROA/DIR:** DIR Topologies §3 C (DL+PCI) - suited to compliance-heavy operations, high-value transfers, and formal verification where every decision must be cryptographically provable.

**Configuration:** All underwriting rules, LLM, agent, and scenarios live in `config.yaml`. Same convention as `samples/31_finance_trading` and `samples/32_fraud_gate`.

---

## How to Run

From the repository root:

```bash
# 1. Install dependencies
pip install -e .
pip install pyyaml

# 2. Run (MockLLM - no Ollama required)
USE_MOCK_LLM=1 python samples/33_insurance_underwriting/run.py
```

**With Ollama (real LLM):**

```bash
ollama serve
ollama pull gemma3:4b
python samples/33_insurance_underwriting/run.py
```

Running `run.py` loads `config.yaml`, processes all scenarios, and generates `report.html` (opened in browser).

---

## Configuration (config.yaml)

All underwriting rules, LLM, agent, and scenario data lives in **`config.yaml`**. No hardcoded values in code.

```yaml
underwriting:
  max_limit: 2000000
  prohibited_industries: ["Fireworks", "CryptoMining"]

llm_defaults:
  model: "gemma3:4b"
  base_url: "http://localhost:11434"

agents:
  - agent_id: "underwriter_agent"
    version: "1.0.0"
    created_by: "compliance@example.com"
    created_at: "2025-02-17T10:00:00Z"
    mission: |
      You are an insurance underwriter. Analyze the client application...
    contract:
      role: EXECUTOR
      max_limit: 2000000
      prohibited_industries: ["Fireworks", "CryptoMining"]
      escalate_on_uncertainty: 0.65

scenarios:
  - name: "Retail"
    business_type: "Retail"
    revenue: 500000
    industry: "Retail"
    expect: "Policy Bound"
  - name: "Fireworks"
    business_type: "Fireworks Factory"
    revenue: 1000000
    industry: "Fireworks"
    expect: "Prohibited Industry"
  - name: "Forged hash"
    business_type: "Fireworks Factory"
    revenue: 1000000
    industry: "Fireworks"
    forge_evidence_hash: true
    expect: "Evidence Invalid"
```

| Section | Purpose |
|---------|---------|
| **underwriting** | `max_limit`, `prohibited_industries` - defaults for contract |
| **llm_defaults** | `model`, `base_url` - Ollama (same as 31, 32). Set `USE_MOCK_LLM=1` for tests without Ollama. |
| **agents** | `agent_id`, `mission`, `contract`, **audit fields** (`version`, `created_by`, `created_at`) |
| **scenarios** | Test cases: `name`, `business_type`, `revenue`, `industry`, `expect`, `forge_evidence_hash` (optional) |

---

## Architecture

### Diagram 1: System Overview

```mermaid
---
config:
  layout: elk
---
flowchart TB
    subgraph CFG["config.yaml"]
        direction TB
        UW["underwriting"]
        LLM["llm_defaults"]
        AG["agents"]
        SC["scenarios"]
    end

    subgraph US["USER SPACE - Probabilistic"]
        ROA["ROAUnderwriterAgent"]
    end

    WALL{{"THE WALL"}}

    subgraph KS["KERNEL SPACE - Deterministic"]
        REG["AgentRegistry"]
        CS["ContextStore"]
        DIM["DIM"]
        LEDGER["DecisionLedger"]
    end

    CFG -->|contract| REG
    CFG -->|scenarios| ROA
    CFG -->|model| ROA

    ROA -->|"PCI + evidence_hash"| WALL
    WALL --> DIM
    REG -->|contract_hash| DIM
    CS -->|context_hash| DIM
    DIM -->|valid only| LEDGER

    style US fill:#fffde7,stroke:#f9a825,color:#333
    style KS fill:#e8f5e9,stroke:#388e3c,color:#333
    style WALL fill:#37474f,color:#fff
    style CFG fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
```

### Diagram 2: Execution Flow (one scenario)

```mermaid
sequenceDiagram
    participant Run as run.py
    participant Agent as ROA Agent
    participant DIM as DIM
    participant Ledger as Ledger

    Run->>Run: load config.yaml
    Run->>Agent: run_decision_cycle(context)

    rect rgb(255, 253, 231)
        Note over Agent: USER SPACE
        Agent->>Agent: 1. Explain (LLM)
        Agent->>Agent: 2. Policy (LLM)
        Agent->>Agent: 3. Self-Check
    end

    Agent-->>Run: PCI + evidence_hash

    Run->>CFG: load_config()
    Run->>Agent: run_decision_cycle(context, forge_evidence_hash?)
    Agent->>Agent: Explain (LLM)
    Agent->>Agent: Policy (LLM)
    Agent->>Agent: Self-Check
    Agent-->>Run: PCI (ProofCarryingIntent)
    Run->>DIM: verify_and_commit(pci, context)
    DIM->>DIM: Recalculate Evidence Hash (Zero Trust)
    DIM->>DIM: Business rules (prohibited, max_limit)
    alt Valid
        DIM->>Ledger: append
        DIM-->>Run: Policy Bound
    else Invalid
        DIM-->>Run: Prohibited Industry / Evidence Invalid / etc.
    end
```

---

## Components

### Kernel Space

| Component | Purpose |
|-----------|---------|
| **AgentRegistry** | Stores the Underwriting Policy (Responsibility Contract): max limit $2M, prohibited industries: Fireworks, CryptoMining |
| **ContextStore** | Holds the Client Application state (business_type, revenue, industry) |
| **DecisionLedger** | Append-only list storing only verified decisions |
| **DecisionIntegrityModule (DIM)** | Proof Checker: recalculates Evidence Hash, rejects on mismatch (Zero Trust) |

### User Space

| Component | Purpose |
|-----------|---------|
| **ROAUnderwriterAgent** | Full ROA agent: Explain(LLM) → Policy(LLM) → Self-Check → PCI with evidence_hash |

---

## ROA Lifecycle (Explain → Policy → Self-Check)

1. **Explain:** LLM interprets client application (narrative, signals, risks, opportunities)
2. **Policy:** LLM proposes COVERAGE_LIMIT, PREMIUM, INDUSTRY (structured output)
3. **Self-Check:** Deterministic check (prohibited industry, max limit): agent may still emit; DIM enforces
4. **PCI:** Build ProofCarryingIntent with evidence_hash, submit to DIM

---

## Evidence Hash Formula

```
Evidence_Hash = SHA256(DFID || Context_Hash || Contract_Hash || Proposal_Params)
```

- **Context_Hash** = SHA256(canonical JSON of ClientApplication)
- **Contract_Hash** = SHA256(canonical JSON of UnderwritingContract)
- **Proposal_Params** = canonical JSON of policy_proposal (coverage_limit, premium, industry)

The DIM **recalculates** this using authoritative Registry and ContextStore data. It never trusts the agent's claimed hash.

---

## Scenarios (from config.yaml)

| Scenario | Input | Expected outcome |
|----------|-------|------------------|
| **Retail** | business_type=Retail, revenue=500k, industry=Retail | Policy Bound |
| **Fireworks** | business_type=Fireworks Factory, industry=Fireworks | Prohibited Industry (LLM may still propose; DIM rejects) |
| **Forged hash** | Same as Fireworks + forge_evidence_hash=true | Evidence Invalid |

---

## HTML Report

After processing, `report.html` is generated in the sample directory and opened in the browser. The report contains:

1. **Input data** – what the agent received (business_type, revenue, industry)
2. **Processing (Explain)** – narrative, signals, risks, opportunities
3. **Applied policy (Policy)** – proposal (coverage_limit, premium, industry) and **audit metadata** (version, created_by, created_at)
4. **Agent Self-Check** – result and reason
5. **DIR (DIM) verification** – Evidence Hash and business rules check
6. **Final outcome** – policy BOUND or REJECTED with reason

---

## File Structure

```
samples/33_insurance_underwriting/
├── README.md               # This file
├── config.yaml             # Underwriting rules, LLM, agents, scenarios
├── run.py                  # Main simulation (config-driven)
├── report_generator.py     # HTML report generator
├── report.html             # Generated audit report (after run)
├── models.py               # Pydantic: UnderwritingContract, ClientApplication, PolicyProposal, ProofCarryingIntent
├── kernel.py               # AgentRegistry, ContextStore, DecisionLedger, DecisionIntegrityModule
├── llm_client.py           # OllamaClient, MockLLM
└── roa_underwriter_agent.py # ROA agent: Explain → Policy → Self-Check → PCI
```

---

## Expected Output

- `Using MockLLM (no Ollama required)` (when USE_MOCK_LLM=1)
- `Contract loaded: version=... created_by=... created_at=...`
- `[Scenario] Retail` / `[Scenario] Fireworks` / `[Scenario] Forged hash`
- `Outcome: Policy Bound (OK)` or `Outcome: Prohibited Industry (OK)` or `Outcome: Evidence Invalid (OK)`
- `Summary` with ledger count and per-scenario results
- `HTML report: ...` (path to report.html)
- Browser opens report.html automatically

---

## Example Run

```
======================================================================
Digital Underwriter - Topology C (ROA + LLM, config-driven)
======================================================================

[Scenario] Retail
  Outcome: Policy Bound (OK)

[Scenario] Fireworks
  Outcome: Prohibited Industry (OK)

[Scenario] Forged hash
  Outcome: Evidence Invalid (OK)

======================================================================
Summary
======================================================================
  Ledger entries (verified only): 1
  Retail: Policy Bound
  Fireworks: Prohibited Industry
  Forged hash: Evidence Invalid

  Day Two prevention: Only verified decisions are bound.
```

---

## Technical Notes

- **Real LLM (default):** Ollama + Gemma. Set `USE_MOCK_LLM=1` for tests without Ollama.
- **Zero API keys:** Uses local Ollama; no cloud API keys required.
- **report.html:** Generated after each run; contains full audit trail (Explain, Policy, Self-Check, DIM verification).

---

## Summary

| Aspect | Description |
|--------|-------------|
| **Topology** | C (Decision Ledger & Proof-Carrying Intents) |
| **Use case** | Digital Underwriter: insurance policy proposals with cryptographic proof of compliance |
| **Agent** | Full ROA: Explain(LLM) → Policy(LLM) → Self-Check → PCI |
| **Config** | config.yaml (underwriting, llm_defaults, agents, scenarios). Same convention as 31, 32, 35. |
| **Input** | ClientApplication (business_type, revenue, industry) |
| **Output** | Policy Bound, or rejection: Evidence Invalid / Prohibited Industry / Coverage Limit Exceeded |
| **Logic** | Agent proposes PCI → DIM recalculates Evidence Hash (Zero Trust) → Business rules → Ledger append if valid |
| **Goal** | Prevent Day Two failures: unverified agent decisions never become binding contracts |
