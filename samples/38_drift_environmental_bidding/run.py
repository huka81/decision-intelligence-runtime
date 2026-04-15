#!/usr/bin/env python3
"""
38_drift_environmental_bidding — Environmental drift (market bidding vs LTV).

Run from repo root:
  python samples/38_drift_environmental_bidding/run.py

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
from shared.config import load_yaml_config

from shared.contracts.provider import YamlContractProvider

from audit_store import AuditStore
from models import BiddingSampleConfig
from pipeline import run_simulation
from report_generator import generate_report
from roi_monitor import BusinessROIMonitor

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    raw = load_yaml_config(sample_dir / "config.yaml")
    cfg = BiddingSampleConfig.model_validate(raw)

    contract_provider = YamlContractProvider(str(sample_dir / "config.yaml"))
    
    try:
        loaded_contract = contract_provider.get_contract(cfg.agent.agent_id)
        # Bidding uses max_bid_usd limit.
        cfg.contract.max_bid_usd = getattr(loaded_contract, "max_drawdown_limit", cfg.contract.max_bid_usd) * 100 # Adjust scaling 
        logger.info(f"Loaded contract from provider: max_bid_usd={cfg.contract.max_bid_usd}")
    except Exception as e:
        logger.warning(f"Could not load contract via provider, using config default: {e}")

    (sample_dir / "data").mkdir(parents=True, exist_ok=True)
    db_path = sample_dir / cfg.paths.database
    if db_path.exists():
        db_path.unlink()

    audit = AuditStore(db_path)
    registry = AgentRegistry(
        str(db_path), supported_versions=cfg.registry.supported_versions
    )
    context_store = ContextStore(str(db_path))

    hs = registry.handshake(
        cfg.agent.agent_id,
        cfg.handshake_contract_dict(),
        cfg.agent.agent_version,
        cfg.agent.priority,
    )
    if not hs.accepted:
        raise SystemExit(f"Handshake failed: {hs.reason}")

    monitor = BusinessROIMonitor(
        audit,
        registry,
        agent_id=cfg.agent.agent_id,
        window_size=cfg.monitor.window_size,
        ltv_usd=cfg.monitor.ltv_usd,
        negative_roi_consecutive_cycles=cfg.monitor.negative_roi_consecutive_cycles,
        suspension_reason=cfg.monitor.suspension_reason,
    )

    print("=" * 64)
    print("Sample 38 - Environmental drift (bidding vs LTV)")
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
        cfg=cfg,
        registry_status=st,
    )

    print()
    print(f"Stopped: {sim.stopped_reason}")
    print(f"HTML report: {report_path}")
    audit.close()
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()

