# Bootstrap Contract Tool (`tools/contract`)

Wizard for creating initial **Bootstrap Responsibility Contracts** (v1.0.0) for ROA agents.

Aligned with:

- ROA Manifesto section 3.1 (canonical nested schema)
- DIR Governance section 2.2 (Bootstrap rule: hard limits on irreversible actions)

## Quick start

From the repository root:

```bash
# Interactive interview
python -m tools.contract init --preset trading --emit both

# Non-interactive (CI or scripted)
python -m tools.contract init --answers my_answers.yaml --emit registry

# Seed from an existing sample config
python -m tools.contract from-sample samples/00_quick_start --non-interactive --emit both

# Validate a registry YAML file
python -m tools.contract validate contracts/trading_bot_01.v1.0.0.yaml --preset trading
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Run interview (or load `--answers`) and emit contract files |
| `validate` | Check canonical YAML against schema + Bootstrap rules |
| `from-sample` | Alias for `init --from-sample <dir>` |

### `init` options

- `--preset` — domain template: `trading`, `fraud_gate`, `underwriting`, `retention_refund`, `generic`, `interface_dmz`, `strategist`, `monitor`
- `--emit` — `sample`, `registry`, or `both` (default: `both`)
- `--out` — output directory (default: `contracts/`)
- `--answers` — YAML file with interview answers (non-interactive)
- `--from-sample` — seed from `samples/<NN>_<use_case>/config.yaml`
- `--agent-id` — pick agent when config has multiple `agents`
- `--non-interactive` — skip prompts when using `--from-sample`

## Emit modes

### Registry (`--emit registry`)

Standalone nested YAML for CI/CD → Agent Registry:

`contracts/<agent_id>.v1.0.0.yaml`

### Sample (`--emit sample`)

Flat fragment compatible with existing `samples/*/config.yaml`:

`contracts/<agent_id>.sample-contract.yaml`

Paste under `contract:` or `agents[].contract`.

## Bootstrap rule

> Every irreversible action class must have a hard numerical limit in v1.0.0.

Presets define required limit keys per domain. `INTERFACE` and `MONITOR` roles have relaxed rules.

## Flatten adapter

Canonical nested contracts are flattened for `dir_core.ResponsibilityContract` (no kernel model change):

| Canonical (`authority`) | Flat (`dir_core`) |
|-------------------------|-------------------|
| `authorized_instruments` | `authorized_instruments` |
| `allowed_policy_types` | `allowed_policy_types` |
| `max_drawdown_limit_pct` (4.0 = 4%) | `max_drawdown_limit` (0.04 fraction) |
| numeric limits | `permissions.<key>` |
| `responsibility.escalate_on_uncertainty` | `escalate_on_uncertainty` |

`INTERFACE` maps to `EXECUTOR` at flatten time because `dir_core` has no INTERFACE role yet.

`YamlContractProvider` in `samples/shared/contracts/provider.py` auto-flattens when `authority` is present.

## Answers file example

```yaml
preset: trading
agent_id: trading_bot_01
owner: jane.doe@example.com
role: EXECUTOR
mission: Execute market orders safely within capital limits.
allowed_policy_types: ["BUY", "SELL", "HOLD"]
authorized_instruments: ["ETH-USD"]
irreversible_limits:
  max_order_size_usd: 50000.0
  max_drawdown_limit_pct: 4.0
explainability: required
evidence_level: high
escalation: mandatory
escalate_on_uncertainty: 0.7
version: "1.0.0"
```

## Cursor interview

Use `.cursor/prompts/contract-bootstrap.prompt.md` for the same interview flow inside Cursor.

## Contract Studio (local web UI)

Interactive chat + live YAML preview with SQLite revision history.

### Install

```bash
pip install -e ".[studio]"
```

### Run

```bash
# Mock LLM (offline demo)
set USE_MOCK_LLM=1
python -m tools.contract.web

# Live Ollama (default in tools/contract/web/llm_config.yaml)
python -m tools.contract.web
```

Open http://127.0.0.1:8765

- **Left:** chat — describe agent parameters in natural language (LLM extracts contract fields)
- **Right:** live canonical YAML preview + Bootstrap validation status
- **Export YAML:** writes `contracts/<agent_id>.v1.0.0.yaml` when Bootstrap passes

### Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONTRACT_STUDIO_DB` | `tools/contract/data/contract_studio.db` | SQLite path |
| `USE_MOCK_LLM` | off | Force deterministic mock LLM |
| `CONTRACT_STUDIO_LLM` | auto | Force `gemini`, `ollama`, or `mock` |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | — | Auto-selects Gemini when set (recommended if Ollama is not running) |

Provider selection is automatic: Gemini key → Gemini; else reachable Ollama → Ollama; else mock.

### SQLite schema

Tables: `contract_sessions`, `chat_messages`, `contract_revisions`, `contract_exports`.  
Every chat turn that updates the contract appends a revision row (full history).

## Out of scope

- Contract Evolution Loop automation (Observe → Publish)
- Agent Registry CI pipeline
- Changing `dir_core` Pydantic models
