# 33 — Digital Underwriter (Topology C / DL+PCI)

Canonical sample: **agent proposes → `dir_core.validate_proposal` validates → ledger → mock bind**.

Injection resistance is architectural: the kernel never treats email prose as permission. The agent returns structured JSON (`total_insured_value`, `territory`, `justification`); DIM validates that proposal against `authority.invariants` in [config.yaml](config.yaml).

## DecisionFlow (one email = one DFID)

1. **Ingest** — load markdown fixture; build coarse `ClientApplication` (industry hint, subject, `mail_body_sha256` only).
2. **ROA (User Space)** — one LLM call reads the email and returns JSON `PolicyProposal` (TiV, territory, justification).
3. **PCI** — emit `ProofCarryingIntent` with `evidence_hash`.
4. **DIM** — `ProofChecker` recomputes hash; `validate_proposal` checks contract IR; append to ledger on `ACCEPT`.
5. **Mock bind** — idempotent `PolicyBindingClient` when DIM returns `Policy Bound`.

The orchestrator maps DIM output to lifecycle: `Policy Bound` → BOUND; sole `AUTHORITY_CEILING` → ESCALATED; any other reject (including multiple codes) → REJECTED. DIM evaluates every invariant and joins all `reason_code` values with `;`.

Audit rows land in `decision_audit_events`. The HTML report is **reconstructed offline** from audit + `emails/` fixtures ([report_generator.py](report_generator.py)).

## Fixtures (MockLLM outcomes)

| File | Typical outcome | `reason_code` |
|------|-----------------|---------------|
| `(EXT) Beaconmere Advisory Ltd - Standard Renewal.md` | BOUND | `POLICY_BOUND` |
| `(EXT) Cryowest Distribution Ltd - High Limit Facility.md` | ESCALATED | `AUTHORITY_CEILING` |
| `(EXT) Nexora Commodities FZE - MENA Property Enquiry.md` | REJECTED | `PROHIBITED_TERRITORY;AUTHORITY_CEILING` |
| `(EXT) Crimson Lane Retail Ltd - Renewal Broker Notes.md` | REJECTED | `PROHIBITED_TERRITORY;AUTHORITY_CEILING` |

Crimson Lane includes jailbreak text in the email; rejection comes from **proposed** Syria territory, not keyword scanning.

## Run

```bash
pip install -e ".[samples]"
USE_MOCK_LLM=1 python samples/33_insurance_underwriting/run.py
```

Regenerate HTML from audit only:

```bash
python samples/33_insurance_underwriting/report_generator.py --simulation-id uw_email_batch_001
```

Env: `USE_MOCK_LLM`, `UNDERWRITING_AUDIT_DB`, `LOG_LEVEL`, `DIR_OPEN_BROWSER=1`.

## Layout

```
orchestrator.py   # DecisionFlow + audit telemetry
agent.py          # User Space ROA (one LLM call → JSON proposal)
kernel.py         # DIM: ProofChecker + validate_proposal + ledger
policy_binding.py # Mock bind + idempotency
telemetry.py      # Audit helpers
report_generator.py  # HTML from decision_audit + emails/
email_fixture_ingest.py
schemas.py
mocks/
emails/
config.yaml
```

## SQLite

```sql
SELECT dfid, event_type, detail_json
FROM decision_audit_events
WHERE json_extract(detail_json, '$.simulation_id') = 'uw_email_batch_001'
ORDER BY id;
```
