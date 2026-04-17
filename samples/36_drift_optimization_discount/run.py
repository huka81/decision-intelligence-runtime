#!/usr/bin/env python3
"""
36_drift_optimization_discount — Optimization drift (reward hacking) in retention discounts.

Topology: classic. Mechanisms: AgentRegistry, ContextStore, ROA (Explain → Policy → Self-Check),
validate_proposal + retention DIM, IdempotencyGuard, StorageBundle telemetry, PerformanceMonitor.

Run from repo root: python samples/36_drift_optimization_discount/run.py
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

from dir_core import DecisionRuntime
from shared.bootstrap import (
    configured_live_llm_is_reachable,
    database_connection_summary,
    setup_environment,
)
from mocks import make_mock_strategy
from performance_monitor import PerformanceMonitor
from pipeline import load_cancellation_inputs, run_simulation
from report_generator import generate_report
from schemas import (  # type: ignore[attr-defined]
    load_retention_full_config,
    load_retention_sample_config_bundle,
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
    max_discount_pct: float,
) -> Dict[str, Any]:
    rc = contracts.get_contract(agent_id)
    payload = rc.model_dump()
    payload["max_discount_pct"] = max_discount_pct
    payload["sample"] = "36_drift_optimization_discount"
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
    config = load_retention_full_config(sample_dir)
    cfg = load_retention_sample_config_bundle(sample_dir)

    seeds = cfg.simulation.seeds or {}
    if seeds.get("retention") is not None:
        cfg = cfg.model_copy(
            update={
                "simulation": cfg.simulation.model_copy(
                    update={"simulation_seed": int(seeds["retention"])}
                )
            }
        )

    simulation_id = cfg.simulation.run_id

    (sample_dir / "data").mkdir(parents=True, exist_ok=True)
    db_rel = (config.get("database") or {}).get("db_path", "data/retention_drift.sqlite")
    primary_db = (sample_dir / Path(str(db_rel))).resolve()
    if primary_db.exists():
        try:
            _unlink_retry(primary_db)
        except PermissionError:
            alt = sample_dir / f"data/retention_drift_run_{os.getpid()}.sqlite"
            logger.warning(
                "Could not remove locked database %s; using %s for this run.",
                primary_db.name,
                alt.name,
            )
            config.setdefault("database", {})["db_path"] = str(
                alt.relative_to(sample_dir).as_posix()
            )

    legacy_audit = sample_dir / "data/retention_audit.sqlite"
    if legacy_audit.exists():
        try:
            _unlink_retry(legacy_audit)
        except PermissionError:
            logger.warning("Could not remove legacy audit database %s.", legacy_audit.name)

    mock_strategy = make_mock_strategy()
    if not configured_live_llm_is_reachable(config):
        config.setdefault("llm_defaults", {})["provider"] = "mock"
    env = setup_environment(
        config,
        mock_llm_strategy=mock_strategy,
        config_path=str(config_path),
    )

    llm = env.llm
    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    runtime = DecisionRuntime(
        bundle,
        supported_versions=cfg.registry.supported_versions,
    )
    registry = runtime.registry
    store = runtime.context_store

    agent_id = cfg.agent.agent_id
    rc = contracts.get_contract(agent_id)
    hs = runtime.register_agent(
        agent_id,
        registry_handshake_payload(
            config,
            contracts,
            agent_id,
            max_discount_pct=cfg.contract.max_discount_pct,
        ),
        cfg.agent.agent_version,
        priority=cfg.agent.priority,
    )
    if not hs.accepted:
        logger.error("Handshake rejected: %s", hs.reason)
        raise SystemExit(1)

    monitor = PerformanceMonitor(
        bundle,
        registry,
        simulation_id=simulation_id,
        agent_id=agent_id,
        window_size=cfg.monitor.window_size,
        avg_threshold_pct=cfg.monitor.avg_threshold_pct,
        suspension_reason=cfg.monitor.suspension_reason,
    )

    logger.info("=" * 64)
    logger.info("Sample 36 - Optimization drift (retention discounts)")
    logger.info("=" * 64)
    logger.info("Inputs: %s", sample_dir / cfg.paths.inputs_file)
    logger.info("Simulation id: %s", simulation_id)
    logger.info("")

    n_inputs = len(load_cancellation_inputs(sample_dir / cfg.paths.inputs_file))
    record_simulation_start(
        bundle,
        simulation_id,
        simulation_id,
        extra={
            "sample": "36_drift_optimization_discount",
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
            llm=llm,
            rc=rc,
            simulation_id=simulation_id,
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

    report_path = generate_report(
        sample_dir,
        bundle,
        simulation_id=simulation_id,
        window=cfg.monitor.window_size,
        agent_id=agent_id,
        max_discount_pct=cfg.contract.max_discount_pct,
        threshold_pct=cfg.monitor.avg_threshold_pct,
        llm_backend=_llm_backend_label(llm),
    )

    logger.info("")
    logger.info("Stopped: %s", sim.stopped_reason)
    logger.info("HTML report: %s", report_path)
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
