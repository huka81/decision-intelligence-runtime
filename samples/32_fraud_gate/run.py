#!/usr/bin/env python3
"""
32_fraud_gate - Real-Time Fraud Gate (Topology B SDS).

DIR Topologies §3: Sovereign Decision Stream. Demonstrates:
- Constrained Decoding (Straightjacket Grammar via Pydantic)
- JIT State Drift validation
- Drift-attack scenario: Agent proposes ALLOW, Runtime rejects STATE_DRIFT_ERROR

Configuration: config.yaml (llm_defaults, agent, jit_validator, scenarios).
Uses real LLM (Ollama/Gemma) by default. Set USE_MOCK_LLM=1 for tests without server.
"""

import hashlib
import json
import logging
import os

from dir_core import new_dfid
from utils.ollama_client import OllamaClient, check_ollama

try:
    from .agent import FraudGuardAgent
    from .config_loader import load_config
    from .execution_engine import execute
    from .jit_validator import validate
    from .llm_client import MockLLM
    from .risk_cache import RiskCache
    from .schemas import TransactionContext
except ImportError:
    from agent import FraudGuardAgent
    from config_loader import load_config
    from execution_engine import execute
    from jit_validator import validate
    from llm_client import MockLLM
    from risk_cache import RiskCache
    from schemas import TransactionContext

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo banner - what this example demonstrates
# ---------------------------------------------------------------------------
BANNER = """
================================================================================
32_fraud_gate - SDS Fraud Gate (DIR Topologies §3: Sovereign Decision Stream)
================================================================================

What this example demonstrates:
  1. LLM (Gemma) evaluates the transaction and returns: ALLOW | BLOCK | CHALLENGE
  2. JIT Validator (Kernel Space) checks: schema, hard limit, STATE DRIFT
  3. Drift Attack: Agent sees user as "clean" -> ALLOW.
     T+50ms external system flags account as "compromised".
     JIT detects state change and REJECT (STATE_DRIFT_ERROR).

Pipeline: Transaction -> Agent (LLM) -> DecisionAtom -> JIT -> Execute (ALLOW only)
================================================================================
"""


def _build_llm(cfg):
    """Build LLM client from config. MockLLM if USE_MOCK_LLM=1 or provider=mock."""
    fallback_rules = cfg.agent.fallback_rules
    if os.getenv("USE_MOCK_LLM", "").strip() in ("1", "true", "yes"):
        logger.info("Using MockLLM (USE_MOCK_LLM=1)")
        return MockLLM(fallback_rules=fallback_rules)
    if cfg.llm is None:
        logger.info("Using MockLLM (no llm_defaults in config)")
        return MockLLM(fallback_rules=fallback_rules)
    llm_cfg = cfg.llm
    model = llm_cfg.effective_model()
    base_url = llm_cfg.effective_base_url()
    logger.info("Using Ollama: model=%s base_url=%s", model, base_url)
    return OllamaClient(model=model, base_url=base_url, timeout=60)


def _check_ollama(cfg) -> bool:
    """Verify Ollama is reachable. Returns False if not (caller may fall back to MockLLM)."""
    if cfg.llm is None:
        return True
    if os.getenv("USE_MOCK_LLM", "").strip() in ("1", "true", "yes"):
        return True
    base_url = cfg.llm.effective_base_url()
    model = cfg.llm.effective_model()
    if not check_ollama(base_url, model):
        logger.warning(
            "Ollama not reachable at %s or model '%s' not found. Use MockLLM. (ollama serve && ollama pull %s)",
            base_url, model, model,
        )
        return False
    return True


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
    global_max_limit: float,
    scenario_label: str = "",
) -> None:
    """Process one transaction through the SDS pipeline."""
    dfid = new_dfid()
    snapshot_id = _snapshot_id(ctx)
    dfid_short = dfid[:8]

    logger.info("")
    logger.info("--- %s ---", scenario_label or tx_id)
    logger.info("[INPUT] tx_id=%s user=%s amount=$%.2f country=%s device=%s velocity_24h=%d",
                tx_id, ctx.user_id, ctx.amount, ctx.geo_country, ctx.device_id, ctx.velocity_24h)

    # 1. Agent decides (sees snapshot state)
    logger.info("[STEP 1] Agent (LLM) evaluates transaction...")
    atom = agent.decide(ctx, dfid=dfid, snapshot_id=snapshot_id)
    logger.info("[AGENT] action=%s reason_code=%s risk_score=%.2f",
                atom.action, atom.reason_code, atom.risk_score)

    # 2. JIT validation
    logger.info("[STEP 2] JIT Validator: schema, hard_limit, state_drift...")
    verdict, reason = validate(atom, risk_cache, snapshot_user_state, global_max_limit=global_max_limit)

    if verdict == "REJECT":
        logger.warning("[JIT] REJECT: %s", reason)
        logger.info("[RESULT] Transaction NOT executed (JIT rejected)")
        return

    logger.info("[JIT] ACCEPT: %s", reason)

    # 3. Execute (only for ALLOW)
    logger.info("[STEP 3] Execution...")
    if atom.action == "ALLOW":
        execute(atom, tx_id)
        logger.info("[RESULT] Transaction EXECUTED (ALLOW)")
    else:
        logger.info("PaymentGateway: %s tx_id=%s (blocked - no execution)", atom.action, tx_id)
        logger.info("[RESULT] Transaction BLOCKED (agent: %s)", atom.action)


def main() -> None:
    print(BANNER, flush=True)
    cfg = load_config()
    ollama_ok = _check_ollama(cfg)
    if ollama_ok:
        llm = _build_llm(cfg)
    else:
        llm = MockLLM(fallback_rules=cfg.agent.fallback_rules)
        if cfg.llm:
            logger.info("Falling back to MockLLM (Ollama not available)")
    risk_cache = RiskCache()
    agent = FraudGuardAgent(
        agent_id=cfg.agent.agent_id,
        risk_cache=risk_cache,
        llm=llm,
        fallback_rules=cfg.agent.fallback_rules,
        mission=cfg.agent.mission,
    )

    for scenario in cfg.scenarios:
        # Populate risk cache from snapshot
        for user_id, state in scenario.snapshot.items():
            risk_cache.set(
                user_id,
                state.get("status", "clean"),
                float(state.get("risk_score", 0.0)),
            )

        ctx = TransactionContext(**scenario.context)
        snapshot = scenario.snapshot

        if scenario.drift_attack:
            # Drift attack: agent decides first, then we flag user
            logger.info("")
            logger.info("--- %s ---", scenario.label)
            logger.info("[INPUT] tx_id=%s user=%s amount=$%.2f country=%s device=%s",
                       scenario.tx_id, ctx.user_id, ctx.amount, ctx.geo_country, ctx.device_id)
            logger.info("[SCENARIO] Agent sees snapshot: user=clean. Decides. Then T+50ms: external system flags account as COMPROMISED.")

            dfid = new_dfid()
            snapshot_id = _snapshot_id(ctx)
            logger.info("[STEP 1] Agent (LLM) evaluates transaction (sees user=clean)...")
            atom = agent.decide(ctx, dfid=dfid, snapshot_id=snapshot_id)
            logger.info("[AGENT] action=%s reason_code=%s", atom.action, atom.reason_code)

            logger.info("[STEP 2] Simulating T+50ms: external system flags user=%s as COMPROMISED", ctx.user_id)
            risk_cache.flag_compromised(ctx.user_id, risk_score=1.0)

            logger.info("[STEP 2] JIT Validator: checking state drift (snapshot vs current)...")
            verdict, reason = validate(atom, risk_cache, snapshot, global_max_limit=cfg.global_max_limit)
            if verdict == "REJECT":
                logger.warning("[JIT] REJECT: %s", reason)
                logger.info("[RESULT] Transaction NOT executed - JIT detected STATE_DRIFT (user status changed clean->compromised)")
            else:
                execute(atom, scenario.tx_id)
        else:
            run_transaction(
                scenario.tx_id,
                ctx,
                agent,
                risk_cache,
                snapshot,
                cfg.global_max_limit,
                scenario_label=scenario.label,
            )

    # Summary
    print("\n" + "=" * 70, flush=True)
    print("SUMMARY - what this example verified:", flush=True)
    print("=" * 70, flush=True)
    print("  1. Legit:         Agent ALLOW  -> JIT ACCEPT  -> transaction EXECUTED", flush=True)
    print("  2. Obvious Fraud: Agent BLOCK  -> JIT ACCEPT  -> transaction BLOCKED (agent)", flush=True)
    print("  3. Drift Attack:  Agent ALLOW  -> JIT REJECT  -> STATE_DRIFT_ERROR (Runtime defended)", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()

