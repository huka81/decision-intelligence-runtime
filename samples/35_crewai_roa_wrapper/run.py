#!/usr/bin/env python3
"""
35_crewai_roa_wrapper — CrewAI crew as ROA User Space with DIM gate (claims refunds).

Topology: classic. Mechanisms: AgentRegistry, ContextStore, validate_proposal (DIM + claims rules),
idempotency_key, StorageBundle telemetry, scenario batch from scenarios.yaml.

Run from repo root: python samples/35_crewai_roa_wrapper/run.py
"""
from __future__ import annotations

import logging
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
_SAMPLE_DIR = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))
if str(_SAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(_SAMPLE_DIR))

from dir_core import AgentRegistry, ContextStore, idempotency_key, new_dfid
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
from agent import resolve_scenario_claim, run_claims_roa_cycle
from contracts import ClaimsContract
from dim import validate_claims_proposal
from mocks import make_mock_strategy
from schemas import CrewConfig, load_scenarios, orders_from_config, registry_claims_contract_payload
from report_generator import write_crewai_claims_html_report
from telemetry import (
    record_agent_decision,
    record_claims_refund_execution,
    record_claims_self_check_failed,
    record_simulation_end,
    record_simulation_start,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _use_crew_ollama(config: Dict[str, Any]) -> bool:
    if os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes"):
        return False
    ld = config.get("llm_defaults") or {}
    if str(ld.get("provider", "")).strip().lower() == "mock":
        return False
    return configured_live_llm_is_reachable(config)


def _llm_backend_label(use_crew_llm: bool, config: Dict[str, Any]) -> str:
    if not use_crew_llm:
        return "Mock (deterministic Crew bypass)"
    ld = dict(config.get("llm_defaults") or {})
    return f"CrewAI→Ollama model={ld.get('model', '')} base_url={ld.get('base_url', '')}"


def _effective_llm_settings(config: Dict[str, Any]) -> Tuple[str, str, float]:
    ld = dict(config.get("llm_defaults") or {})
    model = os.getenv("OLLAMA_MODEL", str(ld.get("model", "gemma3:4b")))
    base = os.getenv("OLLAMA_BASE_URL", str(ld.get("base_url", "http://localhost:11434")))
    temp = float(ld.get("temperature", 0.2))
    return model, base, temp


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)
    scenarios = load_scenarios()
    simulation_id = str((config.get("simulation") or {}).get("run_id", "crewai_claims_run"))
    mock_strategy = make_mock_strategy()

    env = setup_environment(
        config,
        mock_llm_strategy=mock_strategy,
        config_path=str(config_path),
    )
    use_crew_llm = _use_crew_ollama(config)
    if not use_crew_llm:
        env = Environment(
            llm=build_llm_from_config(config, mock_llm_strategy=mock_strategy, force_mock=True),
            repository=env.repository,
            contracts=env.contracts,
        )

    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    agent_rows: List[Dict[str, Any]] = list(config.get("agents") or [])
    if not agent_rows:
        logger.error("config.yaml must define agents[0]")
        return
    agent_row = agent_rows[0]
    agent_id = str(agent_row["agent_id"])
    priority = int(agent_row.get("priority", 10))
    agent_version = str(agent_row.get("version", config.get("agent_version", "1.0.0")))

    rc = contracts.get_contract(agent_id)
    claims_contract = ClaimsContract.from_agent_row(agent_row, rc)
    crew_cfg = CrewConfig.from_dict(agent_row.get("crew", {}))
    dim_contract = registry_claims_contract_payload(config, contracts, agent_id)

    registry = AgentRegistry(storage=bundle.agent_registry)
    store = ContextStore(storage=bundle.context)

    reg_payload = dim_contract
    hr = registry.handshake(agent_id, reg_payload, agent_version=agent_version, priority=priority)
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    llm_model, llm_base, temperature = _effective_llm_settings(config)

    orders = orders_from_config(config)
    dim_ctx: Dict[str, Any] = {"state": {}, "orders": orders}

    record_simulation_start(bundle, simulation_id, llm_backend=_llm_backend_label(use_crew_llm, config))

    results: List[Tuple[str, str, str]] = []
    t0 = time.perf_counter()
    try:
        for scenario in scenarios:
            dfid = new_dfid()
            log_with_dfid(logger, dfid, logging.INFO, "Scenario: %s", scenario.label)

            claim = resolve_scenario_claim(
                scenario.claim,
                scenario.claim_text,
                use_crew_llm=use_crew_llm,
                llm_model=llm_model,
                llm_base_url=llm_base,
                temperature=temperature,
                logger=logger,
                dfid=dfid,
            )
            store.update_session(
                dfid,
                {
                    "claim": claim,
                    "scenario_label": scenario.label,
                },
            )
            store.compile_working_context(agent_id, dfid)

            proposal, roa_err, roa_meta = run_claims_roa_cycle(
                dfid=dfid,
                claim=claim,
                claims_contract=claims_contract,
                crew_cfg=crew_cfg,
                use_crew_llm=use_crew_llm,
                llm_model=llm_model,
                llm_base_url=llm_base,
                temperature=temperature,
                logger=logger,
            )
            explain = str((roa_meta or {}).get("explain_narrative", ""))

            if proposal is None:
                log_with_dfid(logger, dfid, logging.WARNING, "ROA: %s", roa_err)
                record_claims_self_check_failed(
                    bundle,
                    dfid,
                    simulation_id,
                    agent_id=agent_id,
                    reason=str(roa_err or "unknown"),
                    scenario_label=scenario.label,
                    explain_narrative=explain,
                )
                results.append((scenario.label, "SELF_CHECK_FAILED", ""))
                continue

            verdict, reason = validate_claims_proposal(
                proposal,
                dim_ctx,
                claims_contract,
                dim_contract,
                allowed_agents=[agent_id],
            )
            log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", verdict, reason)

            executed = False
            if verdict == ValidationVerdict.ACCEPT:
                oid = str(proposal.params.get("order_id", ""))
                ikey = idempotency_key(
                    dfid,
                    "claims_refund_execute",
                    {"order_id": oid, "amount_eur": proposal.params.get("amount_eur")},
                )
                if bundle.idempotency.get(ikey) is None:
                    bundle.idempotency.set(ikey, {"dfid": dfid, "status": "recorded"})
                    record_claims_refund_execution(
                        bundle,
                        dfid,
                        simulation_id,
                        agent_id=agent_id,
                        policy_kind=proposal.policy_kind,
                        order_id=oid,
                        idempotency_key_value=ikey,
                        amount_eur=float(proposal.params.get("amount_eur") or 0.0),
                    )
                    executed = True
                else:
                    log_with_dfid(logger, dfid, logging.INFO, "Idempotency hit for execution key")

            role_s = str(getattr(rc.role, "value", rc.role))
            record_agent_decision(
                bundle,
                dfid,
                simulation_id,
                agent_id=agent_id,
                policy_kind=proposal.policy_kind,
                verdict=str(verdict),
                reason=str(reason),
                confidence=proposal.confidence,
                justification=str(proposal.justification or ""),
                scenario_label=scenario.label,
                executed=executed,
                order_id=str(proposal.params.get("order_id", "")),
                explain_narrative=explain,
                self_check_passed=True,
                self_check_reason="",
                contract_role=role_s,
                contract_allowed_policy_types=list(rc.allowed_policy_types),
                amount_eur=float(proposal.params.get("amount_eur") or 0.0),
            )

            results.append((scenario.label, str(verdict), scenario.expected))

        record_simulation_end(bundle, simulation_id, status="ok")
    except Exception as e:
        record_simulation_end(bundle, simulation_id, status="error", error_message=str(e))
        raise

    elapsed = time.perf_counter() - t0
    logger.info("SUMMARY / 35_crewai_roa_wrapper (simulation_id=%s, %.2fs)", simulation_id, elapsed)
    for label, verdict, expected in results:
        if verdict == "SELF_CHECK_FAILED":
            ok = ""
        else:
            ok = "OK" if verdict == expected else "UNEXPECTED"
        short = (label[:56] + "…") if len(label) > 56 else label
        logger.info("  [%s] %s expected=%s %s", ok or "FAIL", verdict, expected, short)
    logger.info("=" * 70)

    report_path = write_crewai_claims_html_report(
        bundle,
        simulation_id=simulation_id,
        sample_dir=sample_dir,
        config=config,
        scenario_yaml_count=len(scenarios),
        elapsed_sec=elapsed,
        run_status="ok",
    )
    logger.info("Wrote HTML report: %s", report_path)
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
