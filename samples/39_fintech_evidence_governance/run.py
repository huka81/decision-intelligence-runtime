#!/usr/bin/env python3
"""
39_fintech_evidence_governance — Full §8 semantic defense for credit-limit decisions.

Topology: C — DL+PCI. Mechanisms: Evidence Governance, Semantic Alignment,
ProofCarryingIntent, ProofChecker, DecisionLedger, ApprovalMonitor.

Run from repo root: python samples/39_fintech_evidence_governance/run.py
"""

from __future__ import annotations

import logging
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

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
from dir_core.ledger import DecisionLedger

from approval_monitor import ApprovalMonitor
from limit_client import CreditLimitClient
from mocks import make_mock_strategy
from orchestrator import process_credit_request, process_drift_iteration
from pci_builder import contract_hash_for_agent
from report_generator import generate_report
from schemas import (
    ApprovalMonitorConfig,
    CaseResult,
    CreditLimitGateConfig,
    DriftBatchConfig,
    SemanticAlignmentConfig,
    load_scenarios,
)
from shared.bootstrap import database_connection_summary, setup_environment
from shared.config import load_yaml_config
from telemetry import record_simulation_end, record_simulation_start

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AGENT_ID = "credit_limit_agent"


def _llm_backend_label(llm: Any) -> str:
    name = type(llm).__name__
    if name == "MockLLMClient":
        return "Mock"
    if name == "OllamaClient":
        return f"Ollama model={getattr(llm, 'model', '')}"
    if name == "GeminiClient":
        return f"Gemini model={getattr(llm, 'model', '')}"
    return name


def _summary_line(result: CaseResult) -> str:
    parts = [
        f"scenario={result.scenario_label}",
        f"status={result.final_status}",
        f"executed={result.executed}",
    ]
    if result.proof_ok is not None:
        parts.append(f"proof_ok={result.proof_ok}")
    if result.alignment_flag:
        parts.append(f"alignment_flag={result.alignment_flag}")
    if result.reason:
        parts.append(f"reason={result.reason}")
    return "[SUMMARY] " + " ".join(parts)


def _agents_metadata(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in config.get("agents") or []:
        c = a.get("contract") or {}
        out.append(
            {
                "agent_id": a.get("agent_id"),
                "owner": a.get("owner"),
                "version": a.get("version"),
                "effective_from": a.get("effective_from"),
                "effective_until": a.get("effective_until"),
                "approved_by": a.get("approved_by"),
                "role": c.get("role"),
            }
        )
    return out


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)
    (sample_dir / "data").mkdir(parents=True, exist_ok=True)

    env = setup_environment(
        config,
        mock_llm_strategy=make_mock_strategy(),
        config_path=str(config_path),
    )
    bundle = env.repository
    runtime = DecisionRuntime(bundle)

    contract_row = next(
        (a for a in (config.get("agents") or []) if a.get("agent_id") == AGENT_ID),
        None,
    )
    if not contract_row:
        logger.error("Missing agent %s in config.yaml", AGENT_ID)
        return

    contract = dict((contract_row.get("contract") or {}))
    contract["agent_id"] = AGENT_ID
    hr = runtime.register_agent(
        AGENT_ID,
        contract,
        str(contract_row.get("version", "1.0.0")),
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    simulation_id = str((config.get("simulation") or {}).get("run_id", "run_39"))
    gate_config = CreditLimitGateConfig.from_config(config)
    alignment_config = SemanticAlignmentConfig.from_config(config)
    monitor_config = ApprovalMonitorConfig.from_config(config)
    drift_config = DriftBatchConfig.from_config(config)
    contract_hash = contract_hash_for_agent(contract)

    logger.info("Persistence: %s", database_connection_summary(config))

    t0 = time.perf_counter()
    decisions_total = 0
    executions_total = 0
    status = "ok"
    error_message: str | None = None
    report_path: Path | None = None

    record_simulation_start(
        runtime.audit,
        simulation_id,
        llm_backend=_llm_backend_label(env.llm),
        agents=_agents_metadata(config),
        seeds=(config.get("simulation") or {}).get("seeds"),
    )

    ledger = DecisionLedger()
    limit_client = CreditLimitClient(runtime.audit)
    monitor = ApprovalMonitor(
        bundle,
        runtime.registry,
        simulation_id=simulation_id,
        agent_id=AGENT_ID,
        window_size=monitor_config.window_size,
        threshold=monitor_config.high_risk_approval_rate_threshold,
        suspension_reason=monitor_config.suspension_reason,
        min_income_to_limit_ratio=gate_config.min_income_to_limit_ratio,
    )

    try:
        logger.info("=== Phase A: YAML defense scenarios ===")
        for scenario in load_scenarios():
            result = process_credit_request(
                scenario,
                bundle=bundle,
                runtime=runtime,
                contract=contract,
                contract_hash=contract_hash,
                simulation_id=simulation_id,
                gate_config=gate_config,
                alignment_config=alignment_config,
                limit_client=limit_client,
                ledger=ledger,
            )
            decisions_total += 1
            if result.executed:
                executions_total += 1
            print(_summary_line(result) + "\n")

        logger.info("=== Phase B: Drift batch (async semantic auditing) ===")
        runtime.registry.set_agent_status(AGENT_ID, "ACTIVE", "drift_batch_start")
        drift_raw = config.get("drift_batch") or {}
        phrase = str(drift_raw.get("priority_article_phrase", ""))
        suspended = False
        for i in range(1, drift_config.iterations + 1):
            if suspended:
                break
            result = process_drift_iteration(
                iteration=i,
                bundle=bundle,
                runtime=runtime,
                contract=contract,
                contract_hash=contract_hash,
                simulation_id=simulation_id,
                gate_config=gate_config,
                alignment_config=alignment_config,
                limit_client=limit_client,
                ledger=ledger,
                drift_config=drift_raw,
                chat_phrase=phrase,
            )
            decisions_total += 1
            if result.executed:
                executions_total += 1
            did_suspend, rate = monitor.evaluate_after_execution(result.dfid)
            if did_suspend:
                suspended = True
                print(
                    f"[SUMMARY] drift_batch=SUSPENDED at iteration={i} "
                    f"high_risk_rate={rate}\n"
                )
            elif i == drift_config.iterations or i % 5 == 0:
                print(
                    f"[SUMMARY] drift_iteration={i} executed={result.executed} "
                    f"monitor_rate={rate}\n"
                )

        report_path = generate_report(
            bundle,
            simulation_id=simulation_id,
            sample_dir=sample_dir,
        )
        logger.info("Report: %s", report_path)

    except Exception as exc:
        status = "error"
        error_message = str(exc)
        logger.exception("Run failed: %s", exc)
        raise
    finally:
        elapsed = time.perf_counter() - t0
        record_simulation_end(
            runtime.audit,
            simulation_id,
            status=status,
            decisions_total=decisions_total,
            executions_total=executions_total,
            error_message=error_message,
            elapsed_seconds=elapsed,
        )

    print(
        "\n=== Defense layers exercised ===\n"
        "Layer 1: Evidence Governance (Heuristic + Reconstructed + Cryptographic PCI)\n"
        "Layer 2: Semantic Alignment (proxy gaming — audit and strict modes)\n"
        "Layer 3: Async Approval Monitor (rolling high-risk approval rate drift)\n"
    )

    if report_path and report_path.exists():
        try:
            webbrowser.open(report_path.as_uri())
        except OSError:
            pass


if __name__ == "__main__":
    main()
