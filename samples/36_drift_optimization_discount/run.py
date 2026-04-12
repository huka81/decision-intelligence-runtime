#!/usr/bin/env python3
"""
36_drift_optimization_discount — Optimization drift (reward hacking) in retention discounts.

Run from repo root:
  python samples/36_drift_optimization_discount/run.py

Requires: pip install -e .  and  pip install pyyaml
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
import webbrowser

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import ContextStore
from dir_core.agent_registry import AgentRegistry
from utils.config_loader import load_yaml_config

from audit_store import AuditStore
from models import RetentionSampleConfig
from performance_monitor import PerformanceMonitor
from pipeline import run_simulation
from report_generator import generate_report

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    raw = load_yaml_config(sample_dir / "config.yaml")
    cfg = RetentionSampleConfig.model_validate(raw)

    (sample_dir / "data").mkdir(parents=True, exist_ok=True)
    # Deterministic demo: reset DB each run (see README). Remove legacy triple-file layout if present.
    for rel in (
        cfg.paths.database,
        "data/retention_audit.sqlite",
    ):
        p = sample_dir / rel
        if p.exists():
            p.unlink()

    db_path = str(sample_dir / cfg.paths.database)
    audit = AuditStore(sample_dir / cfg.paths.database)
    registry = AgentRegistry(db_path, supported_versions=cfg.registry.supported_versions)
    context_store = ContextStore(db_path)

    hs = registry.handshake(
        cfg.agent.agent_id,
        cfg.handshake_contract_dict(),
        cfg.agent.agent_version,
        cfg.agent.priority,
    )
    if not hs.accepted:
        raise SystemExit(f"Handshake failed: {hs.reason}")

    monitor = PerformanceMonitor(
        audit,
        registry,
        agent_id=cfg.agent.agent_id,
        window_size=cfg.monitor.window_size,
        avg_threshold_pct=cfg.monitor.avg_threshold_pct,
        suspension_reason=cfg.monitor.suspension_reason,
    )

    print("=" * 64)
    print("Sample 36 - Optimization drift (retention discounts)")
    print("=" * 64)
    print(f"Inputs: {sample_dir / cfg.paths.inputs_file}")
    print(f"Database: {sample_dir / cfg.paths.database}")
    print()

    sim = run_simulation(
        cfg,
        sample_dir=sample_dir,
        audit=audit,
        context_store=context_store,
        monitor=monitor,
        agent_registry=registry,
    )

    st = registry.get_agent_status(cfg.agent.agent_id)
    report_path = generate_report(
        sample_dir,
        audit,
        sim,
        window=cfg.monitor.window_size,
        agent_id=cfg.agent.agent_id,
        registry_status=st,
        max_discount_pct=cfg.contract.max_discount_pct,
        threshold_pct=cfg.monitor.avg_threshold_pct,
    )

    print()
    print(f"Stopped: {sim.stopped_reason}")
    print(f"HTML report: {report_path}")
    audit.close()
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()

