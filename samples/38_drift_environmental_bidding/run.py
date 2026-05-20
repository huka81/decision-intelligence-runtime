#!/usr/bin/env python3
"""
38_drift_environmental_bidding — Environmental drift (market bidding vs LTV).

Topology: B — SDS (snapshot-bound flows, JIT market drift check in DIM extras).
Mechanisms: DIM, AgentRegistry, ContextStore, verify_drift, idempotency_key, decision_audit telemetry.

Run from repo root: python samples/38_drift_environmental_bidding/run.py
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

from dir_core import DecisionRuntime

from pipeline import run_simulation
from report_generator import generate_report
from roi_monitor import BusinessROIMonitor
from schemas import BiddingSampleConfig
from shared.bootstrap import database_connection_summary, setup_environment
from shared.config import load_yaml_config
from telemetry import record_simulation_end

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def mock_strategy(prompt: str, system: Optional[str] = None) -> str:
    """Deterministic LLM output when ``llm_defaults.provider=mock`` (this sample is non-LLM)."""
    return (
        '{"policy_kind": "cpc_bid", "params": {"cpc_bid_usd": 1.0}, '
        '"justification": "Mock deterministic default.", "confidence": 0.94}'
    )


def _first_agent_block(config: Dict[str, Any]) -> Dict[str, Any]:
    agents = config.get("agents") or []
    if not agents:
        raise ValueError("config.yaml must define at least one entry under agents:")
    return agents[0]


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)
    cfg = BiddingSampleConfig.model_validate(config)

    env = setup_environment(
        config,
        mock_llm_strategy=mock_strategy,
        config_path=str(config_path),
    )
    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    runtime = DecisionRuntime(
        bundle,
        supported_versions=cfg.registry.supported_versions,
    )
    registry = runtime.registry
    context_store = runtime.context_store
    audit = runtime.audit

    ab = _first_agent_block(config)
    agent_id = str(ab["agent_id"])
    rc = contracts.get_contract(agent_id)

    hr = runtime.register_agent(
        agent_id,
        rc.model_dump(),
        str(ab.get("agent_version", "1.0.0")),
        priority=int(ab.get("priority", 10)),
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        raise SystemExit(1)

    sim_id = cfg.simulation.run_id
    monitor = BusinessROIMonitor(
        audit,
        registry,
        simulation_id=sim_id,
        agent_id=agent_id,
        window_size=cfg.monitor.window_size,
        ltv_usd=cfg.monitor.ltv_usd,
        negative_roi_consecutive_cycles=cfg.monitor.negative_roi_consecutive_cycles,
        suspension_reason=cfg.monitor.suspension_reason,
    )

    logger.info("Sample 38 - Environmental drift (bidding vs LTV)")
    logger.info("Inputs: %s", sample_dir / cfg.paths.inputs_file)

    try:
        sim = run_simulation(
            cfg,
            sample_dir=sample_dir,
            audit=audit,
            context_store=context_store,
            monitor=monitor,
            agent_registry=registry,
            rc=rc,
            agent_id=agent_id,
            simulation_id=sim_id,
        )
    except Exception as e:
        record_simulation_end(
            audit,
            sim_id,
            status="error",
            stopped_reason="exception",
            details={"error_message": str(e)},
        )
        raise

    st = registry.get_agent_status(agent_id)
    report_path = generate_report(
        sample_dir,
        bundle,
        sim,
        cfg=cfg,
        simulation_id=sim_id,
        registry_status=st,
    )

    logger.info("Stopped: %s", sim.stopped_reason)
    logger.info("HTML report: %s", report_path)
    if os.environ.get("OPEN_REPORT", "1").strip().lower() in ("1", "true", "yes"):
        webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
