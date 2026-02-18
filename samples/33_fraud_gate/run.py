#!/usr/bin/env python3
"""
33_fraud_gate - Real-Time Fraud Gate (Topology B SDS).

DIR Topologies §3: Sovereign Decision Stream. Demonstrates:
- Constrained Decoding (Straightjacket Grammar via Pydantic)
- JIT State Drift validation
- Drift-attack scenario: Agent proposes ALLOW, Runtime rejects STATE_DRIFT_ERROR
"""

import hashlib
import json
import logging

from dir_runtime import new_dfid

try:
    from .agent import FraudGuardAgent
    from .execution_engine import execute
    from .jit_validator import validate
    from .risk_cache import RiskCache
    from .schemas import TransactionContext
except ImportError:
    from agent import FraudGuardAgent
    from execution_engine import execute
    from jit_validator import validate
    from risk_cache import RiskCache
    from schemas import TransactionContext

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _snapshot_id(ctx: TransactionContext) -> str:
    """Generate snapshot ID from transaction context (hash of frozen state)."""
    content = json.dumps(ctx.model_dump(), sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def run_transaction(
    tx_id: str,
    ctx: TransactionContext,
    agent: FraudGuardAgent,
    risk_cache: RiskCache,
    snapshot_user_state: dict,
) -> None:
    """Process one transaction through the SDS pipeline."""
    dfid = new_dfid()
    snapshot_id = _snapshot_id(ctx)
    dfid_short = dfid[:8]

    logger.info(f"[DFID={dfid_short}] Processing tx_id={tx_id} user={ctx.user_id} amount={ctx.amount}")

    # 1. Agent decides (sees snapshot state)
    atom = agent.decide(ctx, dfid=dfid, snapshot_id=snapshot_id)
    logger.info(
        f"[DFID={dfid_short}] Agent proposal: action={atom.action} "
        f"reason={atom.reason_code} risk={atom.risk_score}"
    )

    # 2. JIT validation
    verdict, reason = validate(atom, risk_cache, snapshot_user_state)

    if verdict == "REJECT":
        logger.warning(f"[DFID={dfid_short}] JIT REJECT: {reason}")
        return

    # 3. Execute (only for ALLOW)
    if atom.action == "ALLOW":
        execute(atom, tx_id)
    else:
        logger.info(f"PaymentGateway: {atom.action} tx_id={tx_id} (no execution)")


def main() -> None:
    risk_cache = RiskCache()
    agent = FraudGuardAgent(agent_id="fraud_guard_v1", risk_cache=risk_cache)

    # --- Scenario 1: Legit ---
    user_legit = "user_legit"
    risk_cache.set(user_legit, "clean", 0.05)
    ctx1 = TransactionContext(
        user_id=user_legit,
        amount=50.0,
        geo_country="US",
        device_id="dev_known_001",
        velocity_24h=3,
    )
    snapshot1 = {user_legit: {"status": "clean", "risk_score": 0.05}}
    run_transaction("tx_001", ctx1, agent, risk_cache, snapshot1)

    # --- Scenario 2: Obvious Fraud ---
    user_fraud = "user_fraud"
    risk_cache.set(user_fraud, "clean", 0.0)  # Not in cache yet, or clean - doesn't matter
    ctx2 = TransactionContext(
        user_id=user_fraud,
        amount=10_000.0,
        geo_country="Nigeria",
        device_id="dev_unknown_xyz",
        velocity_24h=1,
    )
    snapshot2 = {user_fraud: {"status": "clean", "risk_score": 0.0}}
    run_transaction("tx_002", ctx2, agent, risk_cache, snapshot2)

    # --- Scenario 3: Drift Attack ---
    user_drift = "user_drift"
    risk_cache.set(user_drift, "clean", 0.1)
    ctx3 = TransactionContext(
        user_id=user_drift,
        amount=100.0,
        geo_country="US",
        device_id="dev_known_002",
        velocity_24h=2,
    )
    snapshot3 = {user_drift: {"status": "clean", "risk_score": 0.1}}

    # Agent sees snapshot (user clean) -> proposes ALLOW
    dfid3 = new_dfid()
    snapshot_id3 = _snapshot_id(ctx3)
    atom3 = agent.decide(ctx3, dfid=dfid3, snapshot_id=snapshot_id3)

    logger.info(
        f"[DFID={dfid3[:8]}] Processing tx_id=tx_003 user={user_drift} amount={ctx3.amount}"
    )
    logger.info(
        f"[DFID={dfid3[:8]}] Agent proposal: action={atom3.action} reason={atom3.reason_code}"
    )

    # T+50ms: External system flags user as Compromised
    risk_cache.flag_compromised(user_drift, risk_score=1.0)

    # JIT: Current state != snapshot -> STATE_DRIFT_ERROR
    verdict3, reason3 = validate(atom3, risk_cache, snapshot3)
    if verdict3 == "REJECT":
        logger.warning(f"[DFID={dfid3[:8]}] JIT REJECT: {reason3}")
    else:
        execute(atom3, "tx_003")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("1. Legit:        Agent ALLOW  -> JIT ACCEPT  -> Executed")
    print("2. Obvious Fraud: Agent BLOCK  -> JIT ACCEPT  -> No execution (blocked)")
    print("3. Drift Attack:  Agent ALLOW  -> JIT REJECT  -> STATE_DRIFT_ERROR")
    print("=" * 60)


if __name__ == "__main__":
    main()
