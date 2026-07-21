#!/usr/bin/env python3
"""
32_fraud_gate — YAML-driven payment fraud gate with ROA, DIM, and JIT drift checks.

Topology: classic + ``scenarios.yaml`` (Sample Development Guide §2).
Mechanisms: AgentRegistry handshake, ContextStore, ROA (Explain -> Policy -> Self-Check),
DIM ``validate_proposal`` with ``verify_drift``, IdempotencyGuard (AuditStore),
``decision_audit_events`` via StorageBundle.

External dependencies used only for demos live under ``mocks/`` (risk store, LLM
strategy, fake PSP). Run from repo root: ``python samples/32_fraud_gate/run.py``.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, cast
import webbrowser

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

_SAMPLE_DIR = Path(__file__).resolve().parent
if str(_SAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(_SAMPLE_DIR))

try:
    import __init__  # noqa: F401
except ImportError:
    pass

from dir_core import DecisionRuntime, new_dfid
from dir_core.data_types import ValidationVerdict
from dir_core.utils.logging_utils import log_with_dfid

from shared.bootstrap import (
    Environment,
    build_llm_from_config,
    configured_live_llm_is_reachable,
    database_connection_summary,
    setup_environment,
)
from shared.config import load_yaml_config

from agent import run_fraud_roa_cycle
from dim import dim_validators
from report_generator import write_fraud_gate_html_report
from schemas import (
    ScenarioConfig,
    TransactionContext,
    fallback_rules_from_config,
    global_max_limit_from_config,
    load_scenarios,
)
from telemetry import (
    record_agent_decision,
    record_simulation_end,
    record_simulation_start,
)
from mocks import (
    InMemoryRiskStore,
    execute_mock_allow_settlement,
    live_risk_rows_from_store,
    log_mock_gateway_non_allow,
    make_mock_strategy,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        model = getattr(llm, "model", "") or ""
        base = getattr(llm, "base_url", "") or ""
        return f"Ollama model={model} base_url={base}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def _run_one_scenario(
    *,
    scenario: ScenarioConfig,
    env: Environment,
    runtime: DecisionRuntime,
    rules: Any,
    contract: Any,
    agent_id: str,
    global_max_limit: float,
    simulation_id: str,
) -> None:
    store = runtime.context_store
    audit = runtime.audit
    risk_store = InMemoryRiskStore()
    for user_id, state in scenario.snapshot.items():
        risk_store.set(
            user_id,
            cast(Any, state.get("status", "clean")),
            float(state.get("risk_score", 0.0)),
        )

    tx = TransactionContext(**scenario.context)
    uid = tx.user_id
    snap_row = scenario.snapshot.get(uid, {})
    snapshot_status = str(snap_row.get("status")) if snap_row else None

    dfid = new_dfid()
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "Scenario=%s tx_id=%s user=%s amount=%s",
        scenario.label,
        scenario.tx_id,
        uid,
        tx.amount,
    )
    store.update_session(
        dfid,
        {
            "transaction": tx.model_dump(),
            "scenario_label": scenario.label,
            "tx_id": scenario.tx_id,
            "simulation_id": simulation_id,
        },
    )
    working = store.compile_working_context(agent_id, dfid)

    roa = run_fraud_roa_cycle(
        env.llm,
        contract,
        tx,
        snapshot_status,
        dfid,
        agent_id,
        rules,
    )
    proposal = roa.proposal
    contract_role = str(contract.role)
    allowed_types = list(contract.allowed_policy_types or [])
    audit_common: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "agent_id": agent_id,
        "scenario_label": scenario.label,
        "tx_id": scenario.tx_id,
        "amount": float(tx.amount),
        "user_id": uid,
        "geo_country": tx.geo_country,
        "device_id": tx.device_id,
        "velocity_24h": int(tx.velocity_24h),
        "contract_role": contract_role,
        "contract_allowed_policy_types": allowed_types,
        "explain_narrative": roa.explain_narrative,
        "explain_signals": roa.explain_signals,
        "explain_risks": roa.explain_risks,
        "explain_opportunities": roa.explain_opportunities,
        "policy_proposed_action": roa.policy_proposed_action,
        "policy_reason_code": roa.policy_reason_code,
        "policy_risk_score": roa.policy_risk_score,
        "policy_stage_confidence": roa.policy_confidence,
        "self_check_passed": roa.self_check_passed,
        "self_check_reason": roa.self_check_reason,
        "drift_attack": scenario.drift_attack,
    }
    if proposal is None:
        log_with_dfid(logger, dfid, logging.WARNING, "Self-check failed; no proposal for scenario %s", scenario.label)
        record_agent_decision(
            audit,
            dfid,
            policy_kind="NONE",
            verdict="REJECT",
            reason="SELF_CHECK_FAILED",
            confidence=0.0,
            justification=roa.policy_justification,
            **audit_common,
        )
        if scenario.expected != "REJECT":
            log_with_dfid(
                logger,
                dfid,
                logging.ERROR,
                "Scenario expected %s but self-check emitted no proposal",
                scenario.expected,
            )
        return

    if scenario.drift_attack:
        log_with_dfid(logger, dfid, logging.INFO, "Simulating post-decision risk flag (TOCTOU) for user=%s", uid)
        risk_store.flag_compromised(uid, risk_score=1.0)

    dim_context: Dict[str, Any] = {
        "meta": working.get("meta", {}),
        "snapshot_user": dict(scenario.snapshot),
        "live_risk": live_risk_rows_from_store(risk_store, scenario.snapshot),
        "global_max_limit": global_max_limit,
    }

    verdict, reason = runtime.evaluate_proposal(
        proposal,
        {},
        dim_context=dim_context,
        allowed_agents=[agent_id],
        contract=contract.model_dump(),
        custom_validators=dim_validators(),
        use_registry_contract=False,
        record_audit=False,
    )
    log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", verdict, reason)

    record_agent_decision(
        audit,
        dfid,
        policy_kind=proposal.policy_kind,
        verdict=str(verdict),
        reason=str(reason),
        confidence=proposal.confidence,
        justification=proposal.justification or "",
        **audit_common,
    )

    exp = scenario.expected.upper()
    got = str(verdict)
    if exp != got:
        log_with_dfid(
            logger,
            dfid,
            logging.ERROR,
            "Scenario %s: expected DIM verdict %s, got %s (%s)",
            scenario.label,
            exp,
            got,
            reason,
        )

    if verdict != ValidationVerdict.ACCEPT:
        log_with_dfid(
            logger,
            dfid,
            logging.INFO,
            "No payment execution (DIM verdict=%s)", verdict
        )
        return

    if proposal.policy_kind == "ALLOW":
        execute_mock_allow_settlement(
            logger,
            audit,
            dfid,
            simulation_id=simulation_id,
            tx_id=scenario.tx_id,
            user_id=uid,
            amount=float(proposal.params.get("amount", 0.0)),
        )
        return

    log_mock_gateway_non_allow(logger, dfid, proposal.policy_kind, scenario.tx_id)


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)
    simulation_id = str((config.get("simulation") or {}).get("run_id", "fraud_gate_demo"))
    rules = fallback_rules_from_config(config)
    global_max_limit = global_max_limit_from_config(config)
    mock_strategy = make_mock_strategy(rules)

    env = setup_environment(
        config,
        mock_llm_strategy=mock_strategy,
        config_path=str(config_path),
    )
    if not configured_live_llm_is_reachable(config):
        env = Environment(
            llm=build_llm_from_config(config, mock_llm_strategy=mock_strategy, force_mock=True),
            repository=env.repository,
            contracts=env.contracts,
        )

    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    runtime = DecisionRuntime(bundle)
    audit = runtime.audit

    scenarios_path = sample_dir / "scenarios.yaml"
    scenarios = load_scenarios(scenarios_path)

    agents_cfg = config.get("agents") or []
    if not agents_cfg:
        logger.error("config.yaml must define at least one agent under agents:")
        return
    agent_id = str(agents_cfg[0].get("agent_id", "fraud_guard_v1"))

    contract = contracts.get_contract(agent_id)
    priority = int(agents_cfg[0].get("priority", 10))
    hr = runtime.register_agent(
        agent_id,
        contract.model_dump(),
        str(config.get("agent_version", "1.0.0")),
        priority=priority,
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    t0 = time.perf_counter()
    run_status = "ok"
    try:
        record_simulation_start(
            audit,
            simulation_id,
            llm_backend=_llm_backend_label(env.llm),
        )
        for scenario in scenarios:
            _run_one_scenario(
                scenario=scenario,
                env=env,
                runtime=runtime,
                rules=rules,
                contract=contract,
                agent_id=agent_id,
                global_max_limit=global_max_limit,
                simulation_id=simulation_id,
            )
        record_simulation_end(audit, simulation_id, status="ok")
    except Exception as exc:
        run_status = "error"
        record_simulation_end(audit, simulation_id, status="error", error_message=str(exc))
        report_path = write_fraud_gate_html_report(
            bundle=bundle,
            simulation_id=simulation_id,
            sample_dir=sample_dir,
            config=config,
            scenario_count=len(scenarios),
            elapsed_sec=time.perf_counter() - t0,
            run_status=run_status,
        )
        logger.info("Report: %s", report_path)
        raise

    report_path = write_fraud_gate_html_report(
        bundle=bundle,
        simulation_id=simulation_id,
        sample_dir=sample_dir,
        config=config,
        scenario_count=len(scenarios),
        elapsed_sec=time.perf_counter() - t0,
        run_status=run_status,
    )
    logger.info("SUMMARY: finished %d scenarios (simulation_id=%s)", len(scenarios), simulation_id)
    logger.info("Report: %s", report_path)

    print(f"\nReport written: {report_path}")
    if os.environ.get("DIR_OPEN_BROWSER") == "1":
        try:
            webbrowser.open(str(report_path.resolve()))
        except Exception as e:
            logger.error("Failed to open report in browser: %s", e)


if __name__ == "__main__":
    main()
