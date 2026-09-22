#!/usr/bin/env python3
"""
33_insurance_underwriting — Digital Underwriter (Decision Ledger and Proof-Carrying Intents).

Topology: C — DL+PCI. Run from repo root: python samples/33_insurance_underwriting/run.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
import webbrowser
from collections import Counter
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
_SAMPLE_DIR = Path(__file__).resolve().parent
for _p in (_REPO_ROOT, _SRC, _SAMPLES, _SAMPLE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core import DecisionRuntime
from dir_core.utils.logging_utils import configure_console_logging
from shared.bootstrap import (
    Environment,
    build_llm_from_config,
    configured_live_llm_is_reachable,
    database_connection_summary,
    setup_environment,
)
from shared.config import load_yaml_config

from mocks import make_mock_strategy
from orchestrator import run_email_pipeline
from report_generator import (
    _events_for_latest_simulation_window,
    _new_report_path,
    generate_email_report,
    group_events_by_dfid,
    terminal_outcome,
)
from telemetry import record_simulation_end, record_simulation_start

configure_console_logging()
logger = logging.getLogger(__name__)


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        return f"Ollama model={getattr(llm, 'model', '')}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def _outcome_summary(audit: Any, simulation_id: str) -> Counter[str]:
    events = _events_for_latest_simulation_window(
        audit.all_events_chronological(), simulation_id
    )
    grouped = group_events_by_dfid(events)
    return Counter(
        str(terminal_outcome(evs).get("outcome", "UNKNOWN"))
        for evs in grouped.values()
    )


def main() -> None:
    sample_dir = _SAMPLE_DIR
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
    logger.info("Persistence: %s", database_connection_summary(config))

    agents_cfg = config.get("agents") or []
    if not agents_cfg:
        logger.error("config.yaml must define agents:")
        return

    agent_row = agents_cfg[0]
    agent_id = str(agent_row.get("agent_id", "underwriter_agent"))
    contract_dict = dict(agent_row.get("contract") or {})
    if not contract_dict:
        logger.error("agents[0].contract is required")
        return

    runtime = DecisionRuntime(bundle)
    hr = runtime.register_agent(
        agent_id,
        contract_dict,
        str(agent_row.get("version", config.get("agent_version", "1.0.0"))),
        priority=int(agent_row.get("priority", 10)),
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    sim = config.get("simulation") or {}
    simulation_id = str(sim.get("run_id", "uw_run"))
    audit = runtime.audit

    run_status = "ok"
    t0 = time.perf_counter()
    dfids: list[str] = []
    try:
        record_simulation_start(
            audit,
            simulation_id,
            llm_backend=_llm_backend_label(llm),
            config=config,
            run_id=simulation_id,
        )

        dfids, _ledger = run_email_pipeline(
            sample_dir,
            config,
            llm,
            bundle,
            registry=runtime.registry,
            audit=audit,
            simulation_id=simulation_id,
            context_store=runtime.context_store,
        )

        db_path = config.get("database", {}).get("db_path", "data/33_insurance_underwriting.db")
        db_path_str = str((sample_dir / db_path).resolve() if not Path(db_path).is_absolute() else db_path)

        run_events = _events_for_latest_simulation_window(
            audit.all_events_chronological(), simulation_id
        )
        counts = _outcome_summary(audit, simulation_id)
        ledger_commits = sum(
            1 for e in run_events if e.get("event") == "LEDGER_COMMITTED"
        )
        logger.info("=" * 70)
        logger.info("Digital Underwriter - Topology C")
        logger.info("=" * 70)
        logger.info("  Emails processed: %s", len(dfids))
        logger.info(
            "  Outcomes: BOUND=%s ESCALATED=%s REJECTED=%s",
            counts.get("BOUND", 0),
            counts.get("ESCALATED", 0),
            counts.get("REJECTED", 0),
        )
        logger.info("  Ledger commits (this run): %s", ledger_commits)
        logger.info("  Audit DB: %s", db_path_str)

        report_path = _new_report_path(sample_dir)
        generate_email_report(
            bundle,
            simulation_id,
            sample_dir,
            config,
            report_path,
        )
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
            counts = _outcome_summary(audit, simulation_id)
            record_simulation_end(
                audit,
                simulation_id,
                status="ok",
                elapsed_seconds=time.perf_counter() - t0,
                decisions_total=len(dfids),
                executions_total=counts.get("BOUND", 0),
                agent_id=agent_id,
            )


if __name__ == "__main__":
    main()
