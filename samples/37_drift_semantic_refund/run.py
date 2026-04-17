#!/usr/bin/env python3
"""
37_drift_semantic_refund — Semantic drift (emotional manipulation) in shipping refunds.

Topology: classic. Mechanisms: setup_environment, AgentRegistry, ContextStore, PolicyProposal,
validate_refund_proposal (DIM), IdempotencyGuard, ComplianceMonitor, StorageBundle telemetry.

Run from repo root: python samples/37_drift_semantic_refund/run.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
import webbrowser
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

from dir_core import AgentRegistry, ContextStore

from compliance_monitor import ComplianceMonitor
from mocks import make_mock_strategy
from pipeline import load_all_tickets, run_simulation
from report_generator import generate_report
from schemas import (  # type: ignore[attr-defined]
    load_refund_full_config,
    load_refund_sample_config_bundle,
)
from shared.bootstrap import (
    configured_live_llm_is_reachable,
    database_connection_summary,
    setup_environment,
)
from telemetry import record_simulation_end, record_simulation_start

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _unlink_retry(path: Path, *, attempts: int = 10, delay_s: float = 0.15) -> None:
    last_err: OSError | None = None
    for _ in range(attempts):
        try:
            path.unlink()
            return
        except PermissionError as e:
            last_err = e
            time.sleep(delay_s)
    if last_err is None:
        raise PermissionError(f"could not unlink: {path}")
    raise last_err


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        return f"Ollama model={getattr(llm, 'model', '')} base_url={getattr(llm, 'base_url', '')}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def registry_handshake_payload(
    config: Dict[str, Any],
    contracts: Any,
    agent_id: str,
    *,
    max_refund_eur: float,
) -> Dict[str, Any]:
    rc = contracts.get_contract(agent_id)
    payload = rc.model_dump()
    payload["max_refund_eur"] = max_refund_eur
    payload["sample"] = "37_drift_semantic_refund"
    row = next(
        (a for a in (config.get("agents") or []) if a.get("agent_id") == agent_id),
        None,
    )
    if row and row.get("mission"):
        payload["mission"] = row["mission"]
    return payload


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_refund_full_config(sample_dir)
    cfg = load_refund_sample_config_bundle(sample_dir)

    seeds = cfg.simulation.seeds or {}
    if seeds.get("refund") is not None:
        cfg = cfg.model_copy(
            update={
                "simulation": cfg.simulation.model_copy(
                    update={"simulation_seed": int(seeds["refund"])}
                )
            }
        )

    simulation_id = cfg.simulation.run_id

    (sample_dir / "data").mkdir(parents=True, exist_ok=True)
    db_rel = (config.get("database") or {}).get("db_path", "data/refund_semantic.sqlite")
    primary_db = (sample_dir / Path(str(db_rel))).resolve()
    if primary_db.exists():
        try:
            _unlink_retry(primary_db)
        except PermissionError:
            alt = sample_dir / f"data/refund_semantic_run_{os.getpid()}.sqlite"
            logger.warning(
                "Could not remove locked database %s; using %s for this run.",
                primary_db.name,
                alt.name,
            )
            config.setdefault("database", {})["db_path"] = str(
                alt.relative_to(sample_dir).as_posix()
            )

    mock_strategy = make_mock_strategy(seed=cfg.simulation.simulation_seed)
    if not configured_live_llm_is_reachable(config):
        config.setdefault("llm_defaults", {})["provider"] = "mock"
    env = setup_environment(
        config,
        mock_llm_strategy=mock_strategy,
        config_path=str(config_path),
    )

    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    registry = AgentRegistry(
        storage=bundle.agent_registry,
        supported_versions=cfg.registry.supported_versions,
    )
    store = ContextStore(storage=bundle.context)

    agent_id = cfg.agent.agent_id
    hs = registry.handshake(
        agent_id,
        registry_handshake_payload(
            config,
            contracts,
            agent_id,
            max_refund_eur=cfg.contract.max_refund_eur,
        ),
        cfg.agent.agent_version,
        cfg.agent.priority,
    )
    if not hs.accepted:
        logger.error("Handshake rejected: %s", hs.reason)
        raise SystemExit(1)

    monitor = ComplianceMonitor(
        bundle,
        registry,
        simulation_id=simulation_id,
        agent_id=agent_id,
        window_size=cfg.monitor.window_size,
        violation_rate_threshold=cfg.monitor.violation_rate_threshold,
        suspension_reason=cfg.monitor.suspension_reason,
        min_delay_hours_for_refund=cfg.monitor.min_delay_hours_for_refund,
    )

    kernel_contract = registry_handshake_payload(
        config,
        contracts,
        agent_id,
        max_refund_eur=cfg.contract.max_refund_eur,
    )

    logger.info("=" * 64)
    logger.info("Sample 37 - Semantic drift (refund policy vs DIM cap)")
    logger.info("=" * 64)
    logger.info("Inputs: %s", sample_dir / cfg.paths.inputs_file)
    logger.info("Simulation id: %s", simulation_id)
    logger.info("")

    n_inputs = len(load_all_tickets(sample_dir, cfg.paths.inputs_file))
    record_simulation_start(
        bundle,
        simulation_id,
        simulation_id,
        extra={
            "sample": "37_drift_semantic_refund",
            "agent_id": agent_id,
            "total_inputs": n_inputs,
        },
    )
    status = "ok"
    err_msg = ""
    sim = None
    try:
        sim = run_simulation(
            cfg,
            sample_dir=sample_dir,
            bundle=bundle,
            context_store=store,
            monitor=monitor,
            agent_registry=registry,
            simulation_id=simulation_id,
            kernel_contract=kernel_contract,
        )
    except Exception as e:
        status = "error"
        err_msg = str(e)
        raise
    finally:
        end_extra: Dict[str, Any] = {}
        if err_msg:
            end_extra["error_message"] = err_msg
        if sim is not None:
            end_extra["stopped_reason"] = sim.stopped_reason
        record_simulation_end(
            bundle,
            simulation_id,
            simulation_id,
            status=status,
            extra=end_extra or None,
        )

    assert sim is not None

    st = registry.get_agent_status(agent_id)
    report_path = generate_report(
        sample_dir,
        bundle,
        simulation_id=simulation_id,
        window=cfg.monitor.window_size,
        agent_id=agent_id,
        registry_status=st,
        max_refund_eur=cfg.contract.max_refund_eur,
        violation_threshold=cfg.monitor.violation_rate_threshold,
        min_delay_hours=cfg.monitor.min_delay_hours_for_refund,
        normal_phase_iterations=cfg.simulation.normal_phase_iterations,
        llm_backend=_llm_backend_label(env.llm),
    )

    logger.info("")
    logger.info("Stopped: %s", sim.stopped_reason)
    logger.info("HTML report: %s", report_path)
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
