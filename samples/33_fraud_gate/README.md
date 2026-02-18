# 33 - Real-Time Fraud Gate (Topology B SDS)

**Goal:** Demonstrate the **Sovereign Decision Stream (SDS)** pattern for high-velocity, structure-first fraud decisions. Uses **Constrained Decoding** (Straightjacket Grammar via Pydantic), **JIT State Drift** validation, and a **drift-attack** scenario where the agent proposes ALLOW but the Runtime rejects with `STATE_DRIFT_ERROR`.

**ROA/DIR:** [DIR Topologies §3](../../docs/03-topologies/DIR_Topologies.md) — suited to real-time fraud gating where the LLM can *only* output valid JSON, and the Runtime must catch state changes between snapshot and execution.

---

## How to run

From the repository root:

```bash
pip install -e .
python samples/33_fraud_gate/run.py
```

With `PYTHONPATH` (if not using `pip install -e .`):

```bash
PYTHONPATH=src python samples/33_fraud_gate/run.py
```

---

## Architecture

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **User Space** | FraudGuardAgent | Produces `DecisionAtom` constrained by `FraudDecisionSchema` (grammar) |
| **Kernel Space** | JITValidator | Fast-Pass: State Drift + Hard Limits |
| **Kernel Space** | ExecutionEngine | Simulates Payment Gateway API call |

```
TransactionContext → FraudGuardAgent → DecisionAtom → JITValidator → ExecutionEngine
                                              ↑
                                    Risk Cache (Redis mock)
```

---

## Scenario: 3 transactions

| # | Scenario | Context | Agent output | JIT result |
|---|----------|---------|--------------|------------|
| 1 | Legit | $50, US, known device | ALLOW | ACCEPT → Executed |
| 2 | Obvious Fraud | $10k, Nigeria, unknown device | BLOCK | ACCEPT → No execution (blocked) |
| 3 | Drift Attack | $100, US, known device; user flagged as "Compromised" at T+50ms | ALLOW | REJECT → STATE_DRIFT_ERROR |

**Drift Attack (key demo):** At T=0 the snapshot shows the user as "clean". The agent reasons and proposes ALLOW. At T+50ms an external system flags the account as "Compromised". The JITValidator detects the state change and rejects—demonstrating why SDS needs the Runtime despite the Agent being "smart".

---

## Schemas

### FraudDecisionSchema (Straightjacket Grammar)

```python
class FraudDecisionSchema(BaseModel):
    action: Literal["ALLOW", "BLOCK", "CHALLENGE"]
    reason_code: str
    risk_score: float = Field(ge=0.0, le=1.0)
```

### DecisionAtom

Extends the schema with `snapshot_id` for JIT drift verification.

---

## Expected output

- `[DFID=...] Processing tx_id=...` for each transaction
- `Agent proposal: action=...`
- `PaymentGateway: ALLOW tx_id=tx_001 ...` for legit tx
- `PaymentGateway: BLOCK tx_id=tx_002 (no execution)` for fraud
- `JIT REJECT: STATE_DRIFT_ERROR...` for drift attack
- Summary table at the end

---

## Technical notes

- **Mocked LLM:** No real outlines/guidance; logic is deterministic to simulate constrained decoding.
- **Risk Cache:** In-memory dict (no Redis); simulates external risk service with controlled updates.
- **Zero API keys:** Fully self-contained; no external services required.
