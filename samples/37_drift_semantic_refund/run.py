#!/usr/bin/env python3
"""
37_drift_semantic_refund — Semantic drift (emotional manipulation) in shipping refunds.

Run from repo root:
  python samples/37_drift_semantic_refund/run.py

Requires: pip install -e .  and  pip install pyyaml
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

from dir_core import ContextStore
from dir_core.agent_registry import AgentRegistry
from dir_core.utils.config_loader import load_yaml_config

from audit_store import AuditStore
from compliance_monitor import ComplianceMonitor
from models import RefundSampleConfig
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
    cfg = RefundSampleConfig.model_validate(raw)

    (sample_dir / "data").mkdir(parents=True, exist_ok=True)
    for rel in (cfg.paths.database,):
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

    monitor = ComplianceMonitor(
        audit,
        registry,
        agent_id=cfg.agent.agent_id,
        window_size=cfg.monitor.window_size,
        violation_rate_threshold=cfg.monitor.violation_rate_threshold,
        suspension_reason=cfg.monitor.suspension_reason,
        min_delay_hours_for_refund=cfg.monitor.min_delay_hours_for_refund,
    )

    print("=" * 64)
    print("Sample 37 - Semantic drift (refund policy vs DIM cap)")
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
        max_refund_eur=cfg.contract.max_refund_eur,
        violation_threshold=cfg.monitor.violation_rate_threshold,
        min_delay_hours=cfg.monitor.min_delay_hours_for_refund,
        normal_phase_iterations=cfg.simulation.normal_phase_iterations,
    )

    print()
    print(f"Stopped: {sim.stopped_reason}")
    print(f"HTML report: {report_path}")
    audit.close()
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()

