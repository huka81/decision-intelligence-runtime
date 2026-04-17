# `mocks/` — test doubles for `32_fraud_gate`

Everything under this directory **stands in for an external system** so the sample runs without Redis, a real PSP, or a live LLM when you use `USE_MOCK_LLM=1` (or unreachable Ollama/Gemini with automatic mock fallback).

| Module | Replaces | Notes |
|--------|----------|--------|
| `external_risk_store.py` | Global risk / account-status API (e.g. Redis) | `InMemoryRiskStore` holds per-user `status` and `risk_score`; `flag_compromised` drives the TOCTOU drift demo. |
| `live_risk_projection.py` | Adapter from that fake into DIM context | Builds the `live_risk` dict passed to `validate_proposal` custom validators. |
| `llm_mock_strategy.py` | Cloud / local LLM | Strategy for `shared.llm.clients.MockLLMClient`; parses ROA prompts using `schemas.FallbackRules`. |
| `settlement_mock.py` | Payment Service Provider | No HTTP; logs and writes `PAYMENT_GATEWAY_ALLOW` audit rows with idempotency keys via `AuditStore`. |

**Not here:** `src/dir_core` (kernel), `samples/shared` (bootstrap), `agent.py` / `dim.py` / `schemas.py` (domain logic), `telemetry.py` and SQLite under `data/` (where artifacts are persisted).
