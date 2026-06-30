#!/usr/bin/env python3
"""
40_retention_airlock — Architecture of Trust retention airlock demo.

Topology: classic
Mechanisms: DecisionRuntime, ROA, DIM (Syntactic + Fact + Evidence), IntentRetryGovernor,
EscalationManager, TemporalGovernanceMonitor

Run from repo root: python samples/40_retention_airlock/run.py
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
for _p in (_SRC, _SAMPLES, _SAMPLE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core import DecisionRuntime
from shared.bootstrap import (
    configured_live_llm_is_reachable,
    database_connection_summary,
    setup_environment,
)

from mocks import make_mock_strategy
from orchestrator import run_defense_scenarios, run_drift_sweep
from report_generator import generate_report
from schemas import (
    DriftSweepConfig,
    RetentionAirlockConfig,
    TemporalMonitorConfig,
    load_sample_config,
    load_scenarios,
)
from telemetry import record_simulation_end, record_simulation_start
from temporal_monitor import TemporalGovernanceMonitor

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

AGENT_ID = "CustomerRetentionAgent"


def _unlink_retry(path: Path, *, attempts: int = 10, delay_s: float = 0.15) -> None:
    last_err: OSError | None = None
    for _ in range(attempts):
        try:
            path.unlink()
            return
        except PermissionError as e:
            last_err = e
            time.sleep(delay_s)
    if last_err is not None:
        raise last_err


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        return f"Ollama model={getattr(llm, 'model', '')}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def registry_handshake_payload(
    config: Dict[str, Any],
    contracts: Any,
    airlock: RetentionAirlockConfig,
) -> Dict[str, Any]:
    rc = contracts.get_contract(AGENT_ID)
    payload = rc.model_dump()
    payload["tier_discount_limits"] = airlock.tier_discount_limits
    payload["sample"] = "40_retention_airlock"
    row = next(
        (a for a in (config.get("agents") or []) if a.get("agent_id") == AGENT_ID),
        None,
    )
    if row and row.get("mission"):
        payload["mission"] = row["mission"]
    return payload


def _print_summary_line(label: str, expected: str, actual: str, reason: str) -> None:
    ok = expected == actual or (expected == "SUSPENDED" and actual in ("SUSPENDED", "REJECT"))
    mark = "OK" if ok else "MISMATCH"
    logger.info(
        "[SUMMARY] %-32s expected=%-10s actual=%-10s %s reason=%s",
        label,
        expected,
        actual,
        mark,
        (reason or "")[:80],
    )


def main() -> None:
    sample_dir = _SAMPLE_DIR
    config_path = sample_dir / "config.yaml"
    config = load_sample_config(sample_dir)
    airlock = RetentionAirlockConfig.from_config(config)
    monitor_cfg = TemporalMonitorConfig.from_config(config)
    drift_cfg = DriftSweepConfig.from_config(config)
    simulation_id = str((config.get("simulation") or {}).get("run_id", "retention_airlock_001"))

    (sample_dir / "data").mkdir(parents=True, exist_ok=True)
    db_rel = (config.get("database") or {}).get("db_path", "data/40_retention_airlock.db")
    primary_db = (sample_dir / Path(str(db_rel))).resolve()
    if primary_db.exists():
        try:
            _unlink_retry(primary_db)
        except PermissionError:
            alt = sample_dir / f"data/40_retention_airlock_{os.getpid()}.db"
            logger.warning("Locked DB %s; using %s", primary_db.name, alt.name)
            config.setdefault("database", {})["db_path"] = str(
                alt.relative_to(sample_dir).as_posix()
            )

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
        supported_versions=str((config.get("registry") or {}).get("supported_versions", "1.x")),
    )
    rc = contracts.get_contract(AGENT_ID)
    agent_row = next(
        (a for a in (config.get("agents") or []) if a.get("agent_id") == AGENT_ID),
        {},
    )
    hs = runtime.register_agent(
        AGENT_ID,
        registry_handshake_payload(config, contracts, airlock),
        str(agent_row.get("version", "1.0.0")),
        priority=int(agent_row.get("priority", 10)),
    )
    if not hs.accepted:
        logger.error("Handshake rejected: %s", hs.reason)
        raise SystemExit(1)

    monitor = TemporalGovernanceMonitor(
        bundle,
        runtime.registry,
        simulation_id=simulation_id,
        agent_id=AGENT_ID,
        window_size=monitor_cfg.window_size,
        avg_threshold_pct=monitor_cfg.avg_threshold_pct,
        suspension_reason=monitor_cfg.suspension_reason,
    )

    scenarios = load_scenarios()
    agents_meta = [
        {
            "agent_id": a.get("agent_id"),
            "owner": a.get("owner"),
            "version": a.get("version"),
            "effective_from": a.get("effective_from"),
            "effective_until": a.get("effective_until"),
            "approved_by": a.get("approved_by"),
            "role": (a.get("contract") or {}).get("role"),
        }
        for a in (config.get("agents") or [])
    ]

    record_simulation_start(
        bundle,
        simulation_id,
        simulation_id,
        extra={
            "sample": "40_retention_airlock",
            "topology": "classic",
            "llm_backend": _llm_backend_label(llm),
            "agents": agents_meta,
            "seeds": (config.get("simulation") or {}).get("seeds", {}),
            "scenario_count": len(scenarios),
        },
    )

    status = "ok"
    err_msg = ""
    phase_a = None
    phase_b = None
    t0 = time.perf_counter()
    try:
        logger.info("=" * 72)
        logger.info("Phase A — Architecture of Trust (defense scenarios)")
        logger.info("=" * 72)
        phase_a = run_defense_scenarios(
            runtime,
            bundle,
            rc,
            llm,
            scenarios,
            airlock,
            simulation_id=simulation_id,
            agent_id=AGENT_ID,
        )
        for row in phase_a.scenarios:
            _print_summary_line(row.label, row.expected, row.final_verdict, row.dim_reason)

        if drift_cfg.enabled:
            logger.info("")
            logger.info("=" * 72)
            logger.info("Phase B — Temporal Governance (margin erosion sweep)")
            logger.info("=" * 72)
            phase_b = run_drift_sweep(
                runtime,
                bundle,
                rc,
                llm,
                drift_cfg,
                airlock,
                monitor,
                simulation_id=simulation_id,
                agent_id=AGENT_ID,
            )
            final_state = "SUSPENDED" if phase_b.suspended else "ACTIVE"
            _print_summary_line(
                "5_temporal_drift_margin_erosion",
                "SUSPENDED",
                final_state,
                phase_b.stopped_reason,
            )
    except Exception as e:
        status = "error"
        err_msg = str(e)
        raise
    finally:
        elapsed = time.perf_counter() - t0
        decisions_total = len(phase_a.scenarios) if phase_a else 0
        if phase_b:
            decisions_total += len(phase_b.steps)
        record_simulation_end(
            bundle,
            simulation_id,
            simulation_id,
            status=status,
            extra={
                "elapsed_seconds": round(elapsed, 3),
                "decisions_total": decisions_total,
                "error_message": err_msg or None,
            },
        )

    report_path = generate_report(
        sample_dir,
        bundle,
        simulation_id=simulation_id,
        agent_id=AGENT_ID,
        monitor_cfg=monitor_cfg,
        airlock=airlock,
        phase_a=phase_a,
        phase_b=phase_b,
        llm_backend=_llm_backend_label(llm),
    )

    logger.info("")
    logger.info("HTML report: %s", report_path)
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
