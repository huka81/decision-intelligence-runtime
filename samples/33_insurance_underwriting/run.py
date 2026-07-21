#!/usr/bin/env python3
"""
33_insurance_underwriting — Digital Underwriter (Decision Ledger and Proof-Carrying Intents).

Topology: C — DL+PCI. Mechanisms: AgentRegistry, ContextStore, ROA (Explain → Policy → Self-Check),
ProofCarryingIntent, ProofChecker, DecisionLedger, AuditStore idempotency, canonical StorageBundle.

Run from repo root: python samples/33_insurance_underwriting/run.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

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

from dir_core import DecisionRuntime
from shared.bootstrap import (
    Environment,
    build_llm_from_config,
    configured_live_llm_is_reachable,
    database_connection_summary,
    setup_environment,
)
from shared.config import load_yaml_config
from shared.contracts.provider import ContractProvider

from orchestrator import run_email_pipeline
from report_generator import generate_email_report
from schemas import UnderwritingContract
from telemetry import record_simulation_end, record_simulation_start
from mocks import make_mock_strategy

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        return f"Ollama model={getattr(llm, 'model', '')} base_url={getattr(llm, 'base_url', '')}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def registry_contract_payload(
    config: Dict[str, Any],
    contracts: ContractProvider,
    agent_id: str,
) -> Dict[str, Any]:
    rc = contracts.get_contract(agent_id)
    base = rc.model_dump()
    row = next(
        (a for a in (config.get("agents") or []) if a.get("agent_id") == agent_id),
        None,
    )
    if not row:
        return base
    extra = dict(row.get("contract") or {})
    merged: Dict[str, Any] = {**base, **extra}
    merged["agent_id"] = agent_id
    if row.get("mission"):
        merged["mission"] = row["mission"]
    return merged


def _new_report_path(sample_dir: Path, slug: str = "emails") -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return results_dir / f"report_{stamp}_{slug}.html"


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)

    if os.environ.get("UNDERWRITING_AUDIT_DB"):
        db = config.setdefault("database", {})
        db["provider"] = "sqlite"
        db["db_path"] = os.environ["UNDERWRITING_AUDIT_DB"]

    mock_strategy = make_mock_strategy()
    env = setup_environment(
        config,
        mock_llm_strategy=mock_strategy,
        config_path=str(config_path),
    )
    if not configured_live_llm_is_reachable(config):
        env = Environment(
            llm=build_llm_from_config(
                config, mock_llm_strategy=mock_strategy, force_mock=True
            ),
            repository=env.repository,
            contracts=env.contracts,
        )

    llm = env.llm
    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    agents_cfg = config.get("agents") or []
    if not agents_cfg:
        logger.error("config.yaml must define agents:")
        return
    agent_id = str(agents_cfg[0].get("agent_id", "underwriter_agent"))

    runtime = DecisionRuntime(bundle)
    registry = runtime.registry
    handshake_contract = registry_contract_payload(config, contracts, agent_id)
    hr = runtime.register_agent(
        agent_id,
        handshake_contract,
        str(agents_cfg[0].get("version", config.get("agent_version", "1.0.0"))),
        priority=int(agents_cfg[0].get("priority", 10)),
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    sim = config.get("simulation") or {}
    simulation_id = str(sim.get("run_id", "uw_run"))

    audit = runtime.audit
    run_status = "ok"
    t0 = time.perf_counter()
    email_results: list[Any] = []
    ledger: Any = None
    try:
        record_simulation_start(
            audit,
            simulation_id,
            llm_backend=_llm_backend_label(llm),
            config=config,
            run_id=str(sim.get("run_id", simulation_id)),
        )

        email_results, ledger = run_email_pipeline(
            sample_dir,
            config,
            llm,
            bundle,
            registry=registry,
            audit=audit,
            simulation_id=simulation_id,
            context_store=runtime.context_store,
        )

        db_path_str = str(
            Path(config.get("database", {}).get("db_path", "data/33_insurance_underwriting.db"))
        )
        if not Path(db_path_str).is_absolute():
            db_path_str = str((sample_dir / db_path_str).resolve())

        contract = UnderwritingContract.model_validate(
            _contract_dict_for_report(config)
        )
        logger.info(
            "Contract loaded: version=%s, created_by=%s, created_at=%s",
            contract.version,
            contract.created_by or "—",
            contract.created_at or "—",
        )

        logger.info("=" * 70)
        logger.info("Digital Underwriter - email orchestrator (Topology C + mock bind)")
        logger.info("=" * 70)

        for case in email_results:
            logger.info("")
            logger.info("[Email] %s", case.source_file)
            logger.info("  DFID: %s", case.dfid)
            for step in case.timeline:
                detail = (step.get("detail") or "")[:120]
                logger.info("    -> %s: %s - %s", step["step"], step["state"], detail)
            logger.info("  Final: %s (%s)", case.final_status, case.reason_code)
            if case.policy_ref:
                logger.info("  Policy ref: %s", case.policy_ref)

        logger.info("")
        logger.info("=" * 70)
        logger.info("Summary")
        logger.info("=" * 70)
        logger.info("  Ledger entries (verified only): %s", len(ledger))
        logger.info("  Audit DB: %s", db_path_str)
        logger.info(
            "  Day Two prevention: Only verified decisions reach the ledger and bind API."
        )

        report_path = _new_report_path(sample_dir)
        generate_email_report(
            email_results=email_results,
            contract=contract.model_dump(),
            ledger_count=len(ledger),
            audit_db_path=db_path_str,
            output_path=report_path,
            email_processing=config.get("email_processing", {}),
        )
        logger.info("")
        logger.info("  HTML report: %s", report_path.resolve())
        if os.environ.get("DIR_OPEN_BROWSER") == "1":
            webbrowser.open(report_path.resolve().as_uri())
    except Exception as exc:
        run_status = "error"
        logger.exception("Run failed: %s", exc)
        record_simulation_end(
            audit,
            simulation_id,
            status="error",
            error_message=str(exc),
            elapsed_seconds=time.perf_counter() - t0,
            agent_id=agent_id,
        )
        raise
    finally:
        if run_status == "ok":
            n_exec = sum(
                1 for c in email_results if getattr(c, "final_status", None) == "BOUND"
            )
            record_simulation_end(
                audit,
                simulation_id,
                status="ok",
                elapsed_seconds=time.perf_counter() - t0,
                decisions_total=len(email_results),
                executions_total=n_exec,
                agent_id=agent_id,
            )


def _contract_dict_for_report(config: Dict[str, Any]) -> Dict[str, Any]:
    uw = config.get("underwriting", {})
    agents = config.get("agents", [])
    agent_cfg = agents[0] if agents else {}
    contract_cfg = agent_cfg.get("contract", {})
    return {
        "agent_id": agent_cfg.get("agent_id", "underwriter_agent"),
        "version": agent_cfg.get("version", "1.0.0"),
        "created_by": agent_cfg.get("created_by"),
        "created_at": agent_cfg.get("created_at"),
        "mission": contract_cfg.get("mission")
        or agent_cfg.get("mission", "Underwrite insurance policies."),
        "max_tiv": contract_cfg.get("max_tiv", uw.get("max_tiv", 2_000_000)),
        "prohibited_industries": contract_cfg.get(
            "prohibited_industries",
            uw.get("prohibited_industries", ["Fireworks", "CryptoMining"]),
        ),
    }


if __name__ == "__main__":
    main()
