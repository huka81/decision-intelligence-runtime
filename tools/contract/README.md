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

Canonical contract ready to paste under `contract:` or `agents[].contract` in
`samples/*/config.yaml`:

`contracts/<agent_id>.sample-contract.yaml`

Both emit modes use the same canonical contract shape. They differ only in file
name and placement intent; the sample mode no longer generates a legacy flat contract.

## Generated contract shape

Every generated YAML has the canonical envelope defined by ROA Manifesto section 3.1:

```yaml
api_version: roa.dir/v1
kind: ResponsibilityContract
metadata:
  contract_id: trading_bot_01
  version: 1.0.0
  owner: jane.doe@example.com
  source_refs: []
subject:
  agent_id: trading_bot_01
  role: EXECUTOR
mission:
  statement: Execute market orders safely within capital limits.
authority:
  allowed_policy_types: [BUY, SELL, HOLD]
  resource_scope:
    instruments: [ETH-USD]
  limits:
    max_order_size_usd: { value: 50000.0, unit: USD }
execution_conditions: {}
responsibility:
  explainability: required
  evidence:
    level: high
    required_attestations: []
  escalation:
    mode: mandatory
    confidence_below: 0.7
governance:
  aggregate_policies: []
```

### Authority vs invariants vs aggregates

Contract Studio injects [`tools/contract/governance/authoring_rules.yaml`](governance/authoring_rules.yaml) into every chat prompt. Three constraint layers must not be mixed:

| Layer | Where it lives | Enforcement | Scope |
|-------|----------------|-------------|-------|
| Authority limit | `authority.limits` | DIM | Single transaction |
| Transaction invariant | `governance_analysis.invariant_candidates` (SQLite only) | DIM | Single proposal predicate |
| Aggregate policy | `governance.aggregate_policies` | MONITOR | Rolling time window |

Bootstrap v1.0.0 may ship with `governance.aggregate_policies: []`. Single-transaction caps belong in `authority.limits`, not aggregate policies with `window: 1t`. Confidence thresholds belong in `responsibility.escalation`, not aggregates.

Typed aggregate policy objects require: `policy_id`, `metric`, `window` (e.g. `24h`, `7d`), `operator`, `threshold`, `unit`, `response` (`SUSPENDED` | `ESCALATION_ONLY` | `DEGRADED`). Studio blocks `INV-*` policy ids, duplicate limits in aggregates, and placeholder identities (`draft_agent`, `owner@example.com`).

Legacy shorthand input is accepted at import boundaries and normalized before
validation. Rendered output never places `agent_id`, `version`, `owner`, `role`,
limits, or escalation fields at the contract root.

```yaml
governance:
  aggregate_policies:
    - policy_id: rolling_drawdown
      metric: rolling_drawdown_pct
      window: 24h
      operator: gt
      threshold: 4.0
      unit: percent
      response: SUSPENDED
      statement: Rolling 24h drawdown must not exceed 4%.
```

## Bootstrap rule

> Every irreversible action class must have a hard numerical limit in v1.0.0.

Presets define required limit keys per domain. `INTERFACE` and `MONITOR` roles have relaxed rules.

## Flatten adapter

Canonical nested contracts are flattened for `dir_core.ResponsibilityContract` (no kernel model change):

| Canonical (`authority`) | Flat (`dir_core`) |
|-------------------------|-------------------|
| `resource_scope.instruments` | `authorized_instruments` |
| `allowed_policy_types` | `allowed_policy_types` |
| `limits.max_drawdown_limit_pct.value` (4.0 = 4%) | `max_drawdown_limit` (0.04 fraction) |
| `limits.<key>.value` | `permissions.<key>` |
| `responsibility.escalation.confidence_below` | `escalate_on_uncertainty` |

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
limit_units:
  max_order_size_usd: USD
  max_drawdown_limit_pct: percent
explainability: required
evidence_level: high
escalation: mandatory
escalate_on_uncertainty: 0.7
version: "1.0.0"
```

`limit_units` is optional for answers files. The tool infers `USD`, `EUR`, and
`percent` from conventional key suffixes, and preserves explicit units imported
from canonical sample contracts.

## Cursor interview

Use `.cursor/prompts/contract-bootstrap.prompt.md` for the same interview flow inside Cursor.

## Contract Studio (local web UI)

Contract Studio is the browser UI for the same canonical Bootstrap Contract
generator. It provides an LLM-assisted interview, governance-aware analysis,
an editable live YAML pane, Bootstrap validation, integrity verification,
and persistent sessions backed by SQLite.

### Governance-aware drafting

Contract Studio injects a versioned **Governance Context Pack**
(`tools/contract/governance/packs/roa-dir-v1.yaml`) curated from
`docs/01-roa-manifesto/ROA_Manifesto.md` and `docs/04-governance/DIR_Governance.md`.

On each chat turn the LLM returns:

- `contract_patch` — partial canonical YAML (exported artifact)
- `governance_analysis` — goal, action classes, invariant candidates, source bindings

Governance analysis, validation reports, and semantic warnings are stored **only
in SQLite** (`governance_context_snapshots`, `revision_governance_assessments`).
They are **not** embedded in exported registry YAML.

| Check type | Blocks export? |
|------------|----------------|
| Schema, Bootstrap, pack integrity, invalid clause refs, AST/SAT | Yes |
| Goal coverage, unclassified actions, ambiguities | No (warnings) |

### Install

```bash
pip install -e ".[studio]"
```

### Run

```bash
# Offline mock (set in config.yaml): studio.use_mock_llm: true
python -m tools.contract.web

# Or one-off override
$env:USE_MOCK_LLM="1"
python -m tools.contract.web
```

The server listens on <http://127.0.0.1:8765>. Put `GEMINI_API_KEY` in
`tools/contract/.env`; everything else belongs in `tools/contract/config.yaml`.

For prompt debugging, set `studio.debug: true` in `config.yaml` and watch the
server console for full system/user prompts and raw LLM responses.

### Studio workflow

1. Select a domain preset and create a session. The preset initializes role,
   policy scope, evidence, and escalation defaults, and supplies domain-specific
   limit suggestions for the interview.
2. Describe the agent's domain, mission, accountable owner, allowed actions, and
  irreversible limits in chat. The LLM returns a canonical contract patch and
  a governance analysis (goal, actions, invariant candidates).
3. After every successful chat turn, Studio normalizes the patch, runs schema +
  Bootstrap + governance validation, renders canonical YAML, and appends an
  immutable revision with governance assessment to SQLite.
4. Review the YAML preview, governance panel, blocking errors, and semantic
  warnings. Warnings do not block export. The session remains `drafting` until
  blocking validation passes; then `ready`.
5. Edit the YAML pane directly when chat is not the fastest route. A **Save**
  button (also `Ctrl+S`) and an `unsaved edits` badge appear as soon as the text
  differs from the stored revision; **Revert** restores it. See
  [Manual YAML editing](#manual-yaml-editing).
6. Use **Verify integrity** to run YAML parsing, canonical schema validation,
  Bootstrap validation, and a SHA-256 content comparison with the stored
  revision.
7. Use **Export YAML** after validation. The current UI always exports `both`:
  a registry file and a canonical sample fragment under `contracts/`. A
  successful export changes the session status to `exported`.

Generated paths use the contract identity and version:

```text
contracts/<agent_id>.v<version>.yaml
contracts/<agent_id>.sample-contract.yaml
```

The session selector restores existing conversations. Sessions can be renamed
or deleted; deletion also removes their messages, revisions, and export records.
Revision history is persisted in SQLite and exposed by the API, although the
current UI displays only the latest revision.

### Manual YAML editing

The YAML pane is a plain editor; `PUT /api/sessions/{id}/contract` saves and
validates in one request:

| Outcome | Response | Persistence |
|---------|----------|-------------|
| YAML unparseable or not a mapping | `saved: false` with `validation_errors` | No revision; stored contract unchanged |
| Parses but fails the canonical schema | `saved: false` with `schema: ...` error | No revision; stored contract unchanged |
| Schema valid, Bootstrap or governance blocking fails | `saved: true`, `validation_ok: false` | New revision, session stays `drafting`, export blocked |
| Fully valid | `saved: true`, `validation_ok: true` | New revision, session becomes `ready` |

A saved edit is normalized and re-rendered from the canonical model, so shorthand
input is rewritten into canonical form and the editor never drifts from the
stored revision. Manual revisions are recorded with change summary
`Manual YAML edit` and reuse the governance analysis of the previous revision,
because no LLM turn took place. Export always uses the stored revision, so the
button is disabled while unsaved edits are pending.

### Provider selection

Studio resolves the chat provider at startup from `tools/contract/config.yaml`
in this order:

1. `studio.use_mock_llm: true` selects the deterministic mock.
2. `studio.llm_provider: gemini|ollama|mock` requests an explicit provider.
3. A `GEMINI_API_KEY` or `GOOGLE_API_KEY` (from `.env`) selects Gemini.
4. A reachable Ollama instance selects Ollama.
5. Otherwise Studio logs a warning and falls back to the mock provider.

An explicitly requested Gemini or Ollama provider also falls back to mock when
its connectivity check fails. Model, base URL, timeout, and Gemini model name
are defined under `llm_defaults` in `tools/contract/config.yaml`.

### Configuration

Non-secret settings live in **`tools/contract/config.yaml`**:

```yaml
studio:
  db_path: data/contract_studio.db
  use_mock_llm: false
  llm_provider: gemini   # or ollama | mock | null (auto)
  debug: false           # log full prompts + raw LLM responses

llm_defaults:
  provider: ollama
  model: gemma3:4b
  base_url: http://localhost:11434
  timeout: 120
  gemini_model: gemini-flash-lite-latest
```

Set `studio.debug: true` to print every system prompt, user prompt, and raw LLM
response to the server log (useful when tuning Contract Studio prompts).

### Secrets (`.env`)

API keys belong **only** in `tools/contract/.env` (see `.env.example`):

```env
GEMINI_API_KEY=
# GOOGLE_API_KEY=
```

On startup, Contract Studio loads the first existing file from:

1. `tools/contract/.env`
2. `.env` at the repository root

Install `python-dotenv` via `pip install -e ".[studio]"`. Variables already set in the
shell are not overridden.

Optional env overrides for tests / one-off runs (not intended for day-to-day
`.env` use): `USE_MOCK_LLM`, `CONTRACT_STUDIO_DB`, `CONTRACT_STUDIO_LLM`,
`CONTRACT_STUDIO_DEBUG`.

### SQLite schema

Tables: `contract_sessions`, `chat_messages`, `contract_revisions`, `contract_exports`,
`governance_context_snapshots`, `revision_governance_assessments`.
Each successful chat turn appends a complete JSON/YAML revision with validation
state, errors, source message, and change summary. Export records retain their
revision, emit mode, and output paths.

## Out of scope

- Contract Evolution Loop automation (Observe → Publish)
- Agent Registry CI pipeline
- Changing `dir_core` Pydantic models
