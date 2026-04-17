#!/usr/bin/env python3
"""
34_langchain_roa_wrapper — LangChain ReAct agent wrapped as ROA User Space with DIM gate.

Topology: classic. Mechanisms: AgentRegistry, ContextStore, validate_proposal (DIM + FinOps extras),
idempotency_key, StorageBundle telemetry, scenario batch from scenarios.yaml.

Run from repo root: python samples/34_langchain_roa_wrapper/run.py
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import webbrowser

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

from dir_core import DecisionRuntime, idempotency_key, new_dfid
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

from agent import run_finops_roa_cycle
from dim import finops_custom_validators
from mocks import make_mock_strategy
from schemas import authoritative_instances_from_config, load_scenarios, registry_contract_payload
from report_generator import write_finops_langchain_html_report
from telemetry import (
    record_agent_decision,
    record_finops_execution,
    record_self_check_failed,
    record_simulation_end,
    record_simulation_start,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def _explain_lists(meta: Dict[str, Any]) -> Tuple[Optional[List[Any]], Optional[List[Any]], Optional[List[Any]]]:
    def _one(key: str) -> Optional[List[Any]]:
        v = meta.get(key)
        return v if isinstance(v, list) and v else None

    return _one("signals"), _one("risks"), _one("opportunities")


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        return f"Ollama model={getattr(llm, 'model', '')} base_url={getattr(llm, 'base_url', '')}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)
    scenarios = load_scenarios()
    simulation_id = str((config.get("simulation") or {}).get("run_id", "lc_finops_run"))
    mock_strategy = make_mock_strategy()

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

    llm = env.llm
    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    runtime = DecisionRuntime(bundle)
    store = runtime.context_store

    agent_rows: List[Dict[str, Any]] = list(config.get("agents") or [])
    if not agent_rows:
        logger.error("config.yaml must define agents[0]")
        return
    agent_id = str(agent_rows[0]["agent_id"])
    priority = int(agent_rows[0].get("priority", 10))
    agent_version = str(agent_rows[0].get("version", config.get("agent_version", "1.0.0")))

    reg_payload = registry_contract_payload(config, contracts, agent_id)
    hr = runtime.register_agent(agent_id, reg_payload, agent_version, priority=priority)
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    auth_instances = authoritative_instances_from_config(config)
    allowed_envs = list(reg_payload.get("allowed_environments") or [])
    llm_defaults = dict(config.get("llm_defaults") or {})
    dim_contract = dict(reg_payload)
    validators = finops_custom_validators()

    record_simulation_start(bundle, simulation_id, llm_backend=_llm_backend_label(llm))

    results: List[Tuple[str, str, str]] = []
    t0 = time.perf_counter()
    try:
        for scenario in scenarios:
            dfid = new_dfid()
            log_with_dfid(logger, dfid, logging.INFO, "Scenario: %s", scenario.label)

            idle = dict(scenario.idle_resources)
            if "instances" not in idle:
                idle = {"instances": []}

            store.update_session(
                dfid,
                {
                    "idle_resources": idle,
                    "scenario_label": scenario.label,
                    "trust_input_labels": scenario.trust_input_labels,
                },
            )
            store.compile_working_context(agent_id, dfid)

            dim_ctx: Dict[str, Any] = {
                "state": {},
                "instances": auth_instances.get("instances", {}),
            }

            contract = contracts.get_contract(agent_id)
            proposal, roa_err, explain_meta = run_finops_roa_cycle(
                llm,
                contract,
                dfid,
                agent_id,
                idle,
                scenario.trust_input_labels,
                llm_defaults,
                allowed_envs,
                show_mission_demo=scenario.show_mission_demo,
            )
            explain_meta = explain_meta or {}
            es, er, eo = _explain_lists(explain_meta)

            if proposal is None:
                log_with_dfid(logger, dfid, logging.WARNING, "ROA: %s", roa_err)
                record_self_check_failed(
                    bundle,
                    dfid,
                    simulation_id,
                    agent_id=agent_id,
                    reason=str(roa_err or "unknown"),
                    scenario_label=scenario.label,
                    explain_narrative=str(explain_meta.get("narrative", "")),
                    explain_signals=es,
                    explain_risks=er,
                    explain_opportunities=eo,
                )
                results.append((scenario.label, "SELF_CHECK_FAILED", ""))
                continue

            verdict, reason = runtime.evaluate_proposal(
                proposal,
                {},
                dim_context=dim_ctx,
                allowed_agents=[agent_id],
                contract=dim_contract,
                custom_validators=validators,
                use_registry_contract=False,
                record_audit=False,
            )
            log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", verdict, reason)

            executed = False
            if verdict == ValidationVerdict.ACCEPT:
                ikey = idempotency_key(
                    dfid,
                    "finops_terminate",
                    {"resource_id": proposal.params.get("resource_id")},
                )
                if bundle.idempotency.get(ikey) is None:
                    bundle.idempotency.set(ikey, {"dfid": dfid, "status": "recorded"})
                    record_finops_execution(
                        bundle,
                        dfid,
                        simulation_id,
                        agent_id=agent_id,
                        policy_kind=proposal.policy_kind,
                        resource_id=str(proposal.params.get("resource_id", "")),
                        idempotency_key_value=ikey,
                    )
                    executed = True
                else:
                    log_with_dfid(logger, dfid, logging.INFO, "Idempotency hit for execution key")

            role_s = str(getattr(contract.role, "value", contract.role))
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
                resource_id=str(proposal.params.get("resource_id", "")),
                explain_narrative=str(explain_meta.get("narrative", "")),
                explain_signals=es,
                explain_risks=er,
                explain_opportunities=eo,
                self_check_passed=True,
                self_check_reason="",
                contract_role=role_s,
                contract_allowed_policy_types=list(contract.allowed_policy_types),
            )

            results.append(
                (scenario.label, str(verdict), str(proposal.params.get("resource_id", "")))
            )

        record_simulation_end(bundle, simulation_id, status="ok")
    except Exception as e:
        record_simulation_end(bundle, simulation_id, status="error", error_message=str(e))
        raise

    elapsed = time.perf_counter() - t0
    report_path = write_finops_langchain_html_report(
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

    logger.info("=" * 70)
    logger.info("SUMMARY — LangChain ROA wrapper / FinOps")
    logger.info("simulation_id=%s", simulation_id)
    for label, verdict, rid in results:
        short = (label[:56] + "…") if len(label) > 56 else label
        logger.info("  %s -> %s resource=%s", short, verdict, rid or "N/A")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
