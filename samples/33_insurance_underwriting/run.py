#!/usr/bin/env python3
"""
33_insurance_underwriting - Digital Underwriter (Decision Ledger & Proof-Carrying Intents).

Default: ingest London Market email fixtures → kernel gates → ROA (Explain → Policy → Self-Check)
→ DIM → Decision Ledger → mock bind API. DFID-tagged SQLite audit + HTML report under results/.

Run: python samples/33_insurance_underwriting/run.py
Env: USE_MOCK_LLM=1, UNDERWRITING_AUDIT_DB=path, LOG_LEVEL=DEBUG
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Allow `python samples/33_insurance_underwriting/run.py` without editable install
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

from models import UnderwritingContract
from shared.config import load_yaml_config
from report_generator import generate_email_report

from pipeline import build_llm, run_email_pipeline

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _new_simulation_report_path(sample_dir: Path) -> Path:
    """
    results/simulation_report_YYYY-MM-DD_HHMM.html (UTC, 24h clock; new file each run).
    """
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return results_dir / f"simulation_report_{stamp}.html"


def build_contract(config: Dict[str, Any]) -> UnderwritingContract:
    uw = config.get("underwriting", {})
    agents = config.get("agents", [])
    agent_cfg = agents[0] if agents else {}
    contract_cfg = agent_cfg.get("contract", {})
    return UnderwritingContract(
        agent_id=agent_cfg.get("agent_id", "underwriter_agent"),
        version=agent_cfg.get("version", "1.0.0"),
        created_by=agent_cfg.get("created_by"),
        created_at=agent_cfg.get("created_at"),
        mission=agent_cfg.get("mission", "Underwrite insurance policies."),
        max_tiv=contract_cfg.get("max_tiv", uw.get("max_tiv", 2_000_000)),
        prohibited_industries=contract_cfg.get(
            "prohibited_industries",
            uw.get("prohibited_industries", ["Fireworks", "CryptoMining"]),
        ),
    )


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)

    use_mock_llm = os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    llm = build_llm(config, use_mock=use_mock_llm)
    if use_mock_llm:
        logger.info("Using MockLLM (no Ollama required)")

    contract = build_contract(config)
    logger.info(
        "Contract loaded: version=%s, created_by=%s, created_at=%s",
        contract.version,
        contract.created_by or "—",
        contract.created_at or "—",
    )

    email_results, ledger, audit = run_email_pipeline(sample_dir, config, llm)
    db_path = Path(
        os.environ.get(
            "UNDERWRITING_AUDIT_DB",
            str(sample_dir / config.get("email_processing", {}).get("audit_db", "data/underwriting_audit.sqlite")),
        )
    )

    print("=" * 70, flush=True)
    print("Digital Underwriter - Email pipeline (Topology C + mock bind)", flush=True)
    print("=" * 70, flush=True)

    for case in email_results:
        print(f"\n[Email] {case.source_file}", flush=True)
        print(f"  DFID: {case.dfid}", flush=True)
        for step in case.timeline:
            detail = (step.get("detail") or "")[:120]
            print(
                f"    -> {step['step']}: {step['state']} - {detail}",
                flush=True,
            )
        print(
            f"  Final: {case.final_status} ({case.reason_code})",
            flush=True,
        )
        if case.policy_ref:
            print(f"  Policy ref: {case.policy_ref}", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("Summary", flush=True)
    print("=" * 70, flush=True)
    print(f"  Ledger entries (verified only): {len(ledger)}", flush=True)
    print(f"  Audit DB: {db_path.resolve()}", flush=True)
    print("\n  Day Two prevention: Only verified decisions reach the ledger and bind API.", flush=True)

    report_path = _new_simulation_report_path(sample_dir)
    generate_email_report(
        email_results=email_results,
        contract=contract.model_dump(),
        ledger_count=len(ledger),
        audit_db_path=str(db_path.resolve()),
        output_path=report_path,
        email_processing=config.get("email_processing", {}),
    )
    print(f"\n  HTML report: {report_path.resolve()}", flush=True)
    audit.close()
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
