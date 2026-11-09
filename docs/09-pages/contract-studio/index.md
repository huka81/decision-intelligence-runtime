---
title: Overview
---

# Contract Studio

**Contract Studio** (`tools/contract`) is a proof-of-concept **Build-Time** tool for creating **Bootstrap Responsibility Contracts** (v1.0.0) for ROA agents. It offers a guided interview, an LLM-assisted browser UI, and a CLI, and it produces the canonical contract YAML that the Agent Registry and the DIM later enforce.

> **Not part of the runtime.** Contract Studio is an authoring tool, not a component of `dir-core`. The runtime never imports `tools.*`; it only consumes the exported contract (via `dir_core.project_contract`). You can use `dir-core` without Studio.

## Why it exists

Writing a contract by hand means turning broad business intent ("retain customers without eroding margin") into precise, reviewable rules. In DIR this is the **Build-Time** part of the Responsibility Contract Lifecycle and the practical side of [Intent Compression](../../04-governance/DIR_Governance.md): one accountable human decision is made once and reused across many autonomous decisions.

Studio supports this process; it does not replace the Contract Owner:

- The LLM only proposes **untrusted drafts** (a contract patch plus a governance analysis).
- Deterministic checks (schema, Bootstrap rule, AST/SAT checks) decide what can be exported.
- A human reviews warnings and accepts the result (**Build-Time HITL**).

Aligned with ROA Manifesto section 3.1 (canonical nested schema) and DIR Governance section 2.2 (**Bootstrap rule**: every irreversible action class has a hard numerical limit in v1.0.0).

## What it does

| Capability | Description |
|------------|-------------|
| **Interview** | Domain presets (`trading`, `fraud_gate`, `underwriting`, `retention_refund`, `generic`, `interface_dmz`, `strategist`, `monitor`) and LLM chat collect mission, owner, allowed actions, and limits. |
| **Governance-aware analysis** | A versioned *Governance Context Pack* curated from the ROA Manifesto and DIR Governance guides the LLM; each turn returns goal, action classes, and invariant candidates with source traceability. |
| **Validation** | Canonical schema, Bootstrap rule, and governance checks. Blocking errors prevent export; semantic warnings (e.g. uncovered goals) do not. |
| **Live YAML editing** | The YAML pane is editable; manual edits are saved, normalized, and re-validated. |
| **Integrity check** | YAML parsing, schema validation, and a SHA-256 comparison with the stored revision. |
| **Revision history** | Sessions, chat messages, immutable revisions, and exports are stored in a local SQLite database. |
| **Export** | A registry file (`contracts/<agent_id>.v<version>.yaml`) and a sample fragment (`contracts/<agent_id>.sample-contract.yaml`). |

### Canonical contract (abridged)

```yaml
api_version: roa.dir/v1
kind: ResponsibilityContract
metadata: { contract_id: trading_bot_01, version: 1.0.0, owner: jane.doe@example.com }
subject: { agent_id: trading_bot_01, role: EXECUTOR }
mission:
  statement: Execute market orders safely within capital limits.
authority:
  allowed_policy_types: [BUY, SELL, HOLD]
  resource_scope: { instruments: [ETH-USD] }
  limits:
    max_order_size_usd: { value: 50000.0, unit: USD }
responsibility:
  explainability: required
  escalation: { mode: mandatory, confidence_below: 0.7 }
governance:
  aggregate_policies: []
```

## Invariants

An **invariant** is a deterministic predicate over a proposed transition that must hold before the Kernel may commit it:

`I_k(s_t, a, s_{t+1}, t) ∈ {0, 1}`

The DIM admits a proposal only when **every** active, applicable invariant evaluates to `1`. This gives *contract-relative enforcement*: an accepted proposal satisfied all machine-verifiable rules of the approved contract version. It does not prove the contract is complete. See [Invariant-Driven Build-Time Governance](../../04-governance/DIR_Governance.md) for the full model.

Contract Studio keeps three constraint layers apart:

| Layer | Where it lives in the contract | Enforced by | Scope |
|-------|--------------------------------|-------------|-------|
| **Authority limit** | `authority.limits` | DIM | Single transaction |
| **Transaction invariant** | `authority.invariants` | DIM | Single proposal predicate |
| **Aggregate policy** | `governance.aggregate_policies` | Monitor / circuit breaker | Rolling time window |

Executable invariants use the runtime `InvariantSpec` shape and one of three types:

| Type | Meaning |
|------|---------|
| `range` | Numeric field must stay within `min` / `max`. |
| `set` | Field must be in `allowed` or must not match `denied` (exact or substring match). |
| `state_match` | Field must match the authoritative state snapshot (with an optional drift envelope). |

Example (from the insurance underwriting sample):

```yaml
authority:
  allowed_policy_types: [BIND]
  invariants:
    - id: INV_TERRITORY
      type: set
      field: params.territory
      denied: ["syria", "damascus"]
      match: substring
      reason_code: PROHIBITED_TERRITORY
    - id: INV_MAX_TIV
      type: range
      field: params.total_insured_value
      max: 3000000
      reason_code: AUTHORITY_CEILING
```

Rules of thumb enforced by Studio:

- Single-transaction caps belong in `authority.limits` or invariants, **not** in aggregate policies with a `1t` window.
- Confidence thresholds belong in `responsibility.escalation`.
- Aggregate policies need `policy_id`, `metric`, `window`, `operator`, `threshold`, `unit`, and `response` (`SUSPENDED`, `ESCALATION_ONLY`, or `DEGRADED`); ids starting with `INV-` are reserved.
- Invariants marked `runtime_amendable` may later be tightened or adjusted within an envelope through a human-gated amendment, without a full contract release (*two-speed contract mutation*).

## Running locally

From the repository root:

```bash
pip install -e ".[studio]"
python -m tools.contract.web
```

The server listens on <http://127.0.0.1:8765>.

- **Offline mode:** set `studio.use_mock_llm: true` in `tools/contract/config.yaml`, or run with `USE_MOCK_LLM=1`, to use a deterministic mock instead of a real LLM.
- **Gemini:** put `GEMINI_API_KEY` in `tools/contract/.env` (see `.env.example`).
- **Ollama:** used automatically when reachable and no Gemini key is present.
- **Configuration:** non-secret settings (database path, provider, model, timeouts, debug logging) live in `tools/contract/config.yaml`.

The provider is selected at startup in this order: mock flag, explicit `studio.llm_provider`, Gemini key, reachable Ollama, then mock as the fallback.

### CLI

The same generator is available without the browser:

```bash
python -m tools.contract init --preset trading --emit both
python -m tools.contract from-sample samples/00_quick_start --non-interactive --emit both
python -m tools.contract validate contracts/trading_bot_01.v1.0.0.yaml --preset trading
```

## Studio workflow

1. Pick a domain **preset** and create a session.
2. Describe the agent's mission, owner, allowed actions, and irreversible limits in **chat**.
3. After each turn Studio normalizes the patch, validates it, and stores a new **revision**.
4. Review the YAML preview, governance panel, errors, and warnings. The session stays `drafting` until blocking checks pass, then becomes `ready`.
5. **Edit the YAML** directly when that is faster (`Ctrl+S` to save, **Revert** to discard).
6. Run **Verify integrity**.
7. **Export YAML**; the session becomes `exported`.

## Scope and limitations

Contract Studio is a proof of concept. Out of scope for now:

- automation of the Contract Evolution Loop (Observe → Publish),
- an Agent Registry CI pipeline,
- changes to the `dir-core` data models.

Governance analysis and validation reports are kept in SQLite only; they are **not** embedded in the exported contract YAML.

## Learn more

- [Governance & Agent Drift](../../04-governance/DIR_Governance.md) - Contract Lifecycle and Invariant-Driven Build-Time Governance
- [Responsibility-Oriented Agents manifesto](../../01-roa-manifesto/ROA_Manifesto.md) - canonical contract schema
- [Samples](../samples/index.md) - contracts used by the runnable scenarios
- [Full tool reference (README)](https://github.com/huka81/decision-intelligence-runtime/blob/main/tools/contract/README.md) - CLI options, answers files, manual-edit API, SQLite schema
