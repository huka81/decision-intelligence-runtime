#!/usr/bin/env python3
"""
08_custom_repo_psql — PostgreSQL-backed canonical StorageBundle.

Topology: classic.
Mechanisms: ``setup_environment``, ``DecisionRuntime``, ROA (Explain → Policy →
Self-Check → Proposal), DIM via ``evaluate_proposal``, ``SIMULATION_START`` /
``SIMULATION_END``, ``AGENT_DECISION``.

Run from repo root: python samples/08_custom_repo_psql/run.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

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

try:
    import __init__  # noqa: F401 — optional package-level side effects (Sample Guide §3)
except ImportError:
    pass

from dir_core import DecisionRuntime, PolicyProposal, new_dfid
from dir_core.data_types import ValidationVerdict
from dir_core.storage import StorageBundle
from dir_core.utils.logging_utils import log_with_dfid

from agent import run_roa_cycle
from mocks import make_mock_strategy
from shared.bootstrap import database_connection_summary, setup_environment
from shared.config import load_yaml_config
from telemetry import record_agent_decision, record_simulation_end, record_simulation_start

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _collect_input(config: Dict[str, Any]) -> Dict[str, Any]:
    demo = config.get("demo") or {}
    return {"note": str(demo.get("note", "PostgreSQL StorageBundle smoke test."))}


def _execute(proposal: PolicyProposal, bundle: StorageBundle, dfid: str) -> None:
    """Gated execution hook — this demo persists only via the StorageBundle audit path."""
    _ = (proposal, bundle, dfid)


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)
    sim = config.get("simulation") or {}
    simulation_id = str(sim.get("run_id", "psql08"))

    # 1. Bootstrap: LLM, StorageBundle, ContractProvider (Sample Guide §4, §10).
    env = setup_environment(
        config,
        mock_llm_strategy=make_mock_strategy(config),
        config_path=str(config_path),
    )
    llm = env.llm
    bundle = env.repository
    contracts = env.contracts
    logger.info("Persistence: %s", database_connection_summary(config))

    agents_cfg = config.get("agents") or []
    if not agents_cfg:
        logger.error("config.yaml must define at least one agent under agents:")
        return
    agent_row = agents_cfg[0]
    agent_id = str(agent_row.get("agent_id", "repo_demo_agent"))
    priority = int(agent_row.get("priority", 10))
    contract = contracts.get_contract(agent_id)
    agent_version = str(agent_row.get("version") or config.get("agent_version", "1.0.0"))

    # 2. Kernel facade over the canonical bundle.
    runtime = DecisionRuntime(bundle)

    # 3. Handshake before any proposal (same contract surface as ``AgentRegistry.handshake``).
    hr = runtime.register_agent(
        agent_id,
        contract.model_dump(mode="json"),
        agent_version,
        priority=priority,
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    t0 = time.perf_counter()
    decisions_total = 0
    executions_total = 0
    run_status = "ok"
    end_error: Optional[str] = None
    caught_exc: Optional[BaseException] = None
    verdict_str = "n/a"

    try:
        record_simulation_start(
            runtime.audit,
            simulation_id,
            config,
            llm_backend=llm.__class__.__name__,
            topology="classic",
        )

        # 4. Decision flow (DFID) and compiled context.
        dfid = new_dfid()
        store = runtime.context_store
        store.update_session(dfid, {"input": _collect_input(config)})
        ctx = store.compile_working_context(agent_id, dfid)
        ctx = dict(ctx)
        ctx["meta"] = {"dfid": dfid, "agent_id": agent_id}

        # 5. ROA lifecycle (User Space).
        proposal, explain_narrative, self_fail = run_roa_cycle(
            llm, contract, ctx, dfid, agent_id
        )
        if proposal is None:
            log_with_dfid(
                logger,
                dfid,
                logging.WARNING,
                "Self-check failed; no proposal: %s",
                self_fail,
            )
            record_agent_decision(
                runtime.audit,
                dfid,
                simulation_id=simulation_id,
                agent_id=agent_id,
                policy_kind="(none)",
                verdict="SELF_CHECK_FAILED",
                reason=self_fail,
                confidence=0.0,
                justification="",
                explain_narrative=explain_narrative,
            )
            decisions_total = 1
        else:
            # 6. DIM (Kernel Space).
            verdict, reason = runtime.evaluate_proposal(
                proposal,
                {},
                dim_context=ctx,
                allowed_agents=[agent_id],
                record_audit=False,
            )
            verdict_str = str(verdict)
            log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", verdict_str, reason)

            # 7. Telemetry (canonical audit API only).
            record_agent_decision(
                runtime.audit,
                dfid,
                simulation_id=simulation_id,
                agent_id=agent_id,
                policy_kind=proposal.policy_kind,
                verdict=verdict_str,
                reason=str(reason),
                confidence=proposal.confidence,
                justification=str(proposal.justification or ""),
                explain_narrative=explain_narrative,
            )
            decisions_total = 1

            # 8. Execution gated by DIM verdict only.
            if verdict == ValidationVerdict.ACCEPT:
                _execute(proposal, bundle, dfid)
                if proposal.policy_kind != "HOLD":
                    log_with_dfid(
                        logger,
                        dfid,
                        logging.INFO,
                        "ACCEPT on non-HOLD policy — this demo does not execute side effects.",
                    )

    except Exception as exc:
        caught_exc = exc
        run_status = "error"
        end_error = str(exc)
        logger.exception("Run failed: %s", exc)
    finally:
        elapsed = time.perf_counter() - t0
        record_simulation_end(
            runtime.audit,
            simulation_id,
            status=run_status,
            error_message=end_error,
            elapsed_seconds=elapsed,
            decisions_total=decisions_total,
            executions_total=executions_total,
        )

    if caught_exc is not None:
        raise caught_exc

    logger.info(
        "SUMMARY / 08_custom_repo_psql simulation_id=%s elapsed=%.2fs DIM=%s",
        simulation_id,
        elapsed,
        verdict_str,
    )


if __name__ == "__main__":
    main()
