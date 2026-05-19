"""
Simulation loop: market JSON, ContextSnapshot, ROA (simulated), DIM + JIT, telemetry, ROI monitor.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dir_core import AgentRegistry, ContextStore, idempotency_key, new_dfid
from dir_core.data_types import ValidationVerdict
from dir_core.models import ContextSnapshot
from dir_core.storage.base import AuditStore
from dir_core.utils.logging_utils import log_with_dfid

from agent import run_bidding_roa_cycle
from dim import validate_bidding_proposal
from roi_monitor import BusinessROIMonitor
from schemas import BiddingSampleConfig, max_cpc_ceiling_usd
from telemetry import (
    record_context_compiled,
    record_cpc_bid_executed,
    record_dim_validation,
    record_policy_proposal,
    record_simulation_end,
    record_simulation_start,
)

logger = logging.getLogger(__name__)


def load_market_cycles(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array of cycles: {path}")
    return data


@dataclass
class CycleRecord:
    cycle_id: str
    search_term: str
    market_cpc_to_win: float
    impressions_available: int
    channel: str
    campaign_id: str


def row_to_cycle(row: Dict[str, Any]) -> CycleRecord:
    return CycleRecord(
        cycle_id=str(row["cycle_id"]),
        search_term=str(row.get("search_term", "")),
        market_cpc_to_win=float(row["market_cpc_to_win"]),
        impressions_available=int(row.get("impressions_available", 0)),
        channel=str(row.get("channel", "")),
        campaign_id=str(row.get("campaign_id", "")),
    )


def load_all_cycles(sample_dir: Path, inputs_file: str) -> List[CycleRecord]:
    path = sample_dir / inputs_file
    if not path.exists():
        raise FileNotFoundError(f"Market input file not found: {path}")
    return [row_to_cycle(r) for r in load_market_cycles(path)]


@dataclass
class SimulationStep:
    iteration: int
    dfid: str
    cycle_id: str
    search_term: str
    market_cpc_to_win: float
    bid_usd: float
    dim_verdict: str
    dim_reason: str
    executed: bool
    rolling_avg_cpc_after: Optional[float] = None
    roi_estimate_after: Optional[float] = None
    console_note: str = ""


@dataclass
class SimulationResult:
    steps: List[SimulationStep] = field(default_factory=list)
    stopped_reason: str = ""
    total_inputs: int = 0
    suspension_decision_number: Optional[int] = None


def run_simulation(
    cfg: BiddingSampleConfig,
    *,
    sample_dir: Path,
    audit: AuditStore,
    context_store: ContextStore,
    monitor: BusinessROIMonitor,
    agent_registry: AgentRegistry,
    rc: Any,
    agent_id: str,
    simulation_id: str,
) -> SimulationResult:
    cycles = load_all_cycles(sample_dir, cfg.paths.inputs_file)
    n = len(cycles)
    result = SimulationResult(total_inputs=n)
    sim_id = simulation_id
    max_cpc = max_cpc_ceiling_usd(rc)
    margin = cfg.simulation.bid_margin_above_market
    allowed = cfg.dim.allowed_agents or [agent_id]
    ltv = cfg.monitor.ltv_usd

    t0 = time.perf_counter()
    record_simulation_start(
        audit,
        sim_id,
        details={"total_cycles": n, "agent_id": agent_id},
    )

    logged_early = False
    logged_late = False
    logged_roi_positive_window = False

    for i, cyc in enumerate(cycles):
            st = agent_registry.get_agent_status(agent_id)
            if st and st[0] == "SUSPENDED":
                result.stopped_reason = "agent_already_suspended"
                break

            dfid = new_dfid()
            cref = cyc.cycle_id
            market = cyc.market_cpc_to_win
            bid = min(market + margin, max_cpc)

            snap_data: dict[str, Any] = {
                "cycle_id": cref,
                "search_term": cyc.search_term,
                "market_cpc_to_win": market,
                "impressions_available": cyc.impressions_available,
                "channel": cyc.channel,
                "campaign_id": cyc.campaign_id,
                "compiled_for": agent_id,
            }
            snapshot = ContextSnapshot.create(dfid, snap_data, source="context_compiler")

            context_store.update_session(
                dfid,
                {
                    "market": {
                        "cycle_id": cref,
                        "search_term": cyc.search_term,
                        "market_cpc_to_win": market,
                        "impressions_available": cyc.impressions_available,
                        "channel": cyc.channel,
                        "campaign_id": cyc.campaign_id,
                    },
                    "snapshot_id": snapshot.snapshot_id,
                },
            )

            ctx_dim: Dict[str, Any] = {
                "state": dict(cfg.dim.context_state),
                "market_snapshot": dict(snap_data),
                "market_live": dict(snap_data),
            }

            record_context_compiled(
                audit,
                dfid,
                sim_id,
                details={
                    "cycle_id": cref,
                    "market_cpc_to_win": market,
                    "snapshot_id": snapshot.snapshot_id,
                },
                agent_id=agent_id,
                causation_id=dfid,
            )

            proposal, roa_audit = run_bidding_roa_cycle(
                dfid=dfid,
                agent_id=agent_id,
                contract=rc,
                market_cpc_to_win=market,
                bid_usd=bid,
                cycle_index=i,
                total_cycles=n,
                snapshot_id=snapshot.snapshot_id,
            )

            if proposal is None:
                log_with_dfid(
                    logger,
                    dfid,
                    logging.WARNING,
                    "Self-check failed; no proposal: %s",
                    roa_audit.get("self_check_reason", ""),
                )
                step = SimulationStep(
                    iteration=i,
                    dfid=dfid,
                    cycle_id=cref,
                    search_term=cyc.search_term,
                    market_cpc_to_win=market,
                    bid_usd=bid,
                    dim_verdict="REJECT",
                    dim_reason="SELF_CHECK_FAILED",
                    executed=False,
                    console_note="SELF_CHECK",
                )
                result.steps.append(step)
                continue

            record_policy_proposal(
                audit,
                dfid,
                sim_id,
                details={
                    "cpc_bid_usd": bid,
                    "policy_kind": proposal.policy_kind,
                    "explain_narrative": roa_audit.get("explain_narrative", ""),
                    "self_check_passed": roa_audit.get("self_check_passed"),
                },
                agent_id=agent_id,
                causation_id=dfid,
            )

            verdict, reason = validate_bidding_proposal(
                proposal,
                ctx_dim,
                allowed,
                rc,
            )
            verdict_s = verdict.value if isinstance(verdict, ValidationVerdict) else str(verdict)
            reason_s = reason.value if hasattr(reason, "value") else str(reason)

            record_dim_validation(
                audit,
                dfid,
                sim_id,
                verdict=verdict_s,
                reason=reason_s,
                agent_id=agent_id,
                causation_id=dfid,
            )

            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "DIM: %s %s",
                verdict_s,
                reason_s,
            )

            step = SimulationStep(
                iteration=i,
                dfid=dfid,
                cycle_id=cref,
                search_term=cyc.search_term,
                market_cpc_to_win=market,
                bid_usd=bid,
                dim_verdict=verdict_s,
                dim_reason=reason_s,
                executed=False,
            )

            if verdict_s != "ACCEPT":
                step.console_note = "DIM_REJECT"
                result.steps.append(step)
                continue

            ikey = idempotency_key(
                dfid,
                "cpc_bid",
                {"cpc_bid_usd": bid, "cycle_id": cref},
            )
            record_cpc_bid_executed(
                audit,
                dfid,
                sim_id,
                cpc_bid_usd=bid,
                market_cpc_to_win=market,
                cycle_id=cref,
                idempotency_key=ikey,
                extra={"policy_kind": proposal.policy_kind},
                agent_id=agent_id,
                causation_id=dfid,
            )
            step.executed = True

            stop, avg_after = monitor.evaluate_after_execution(dfid)
            step.rolling_avg_cpc_after = avg_after
            if avg_after is not None:
                step.roi_estimate_after = ltv - avg_after

            if not logged_early and i == 0:
                logged_early = True
                if avg_after is None:
                    m_note = " Monitor OK (window not full)."
                elif ltv > avg_after + 1e-9:
                    m_note = (
                        f" ROI positive (LTV {ltv:.2f} > avg CPC {avg_after:.2f}) - Monitor OK."
                    )
                else:
                    m_note = (
                        f" Rolling window full; avg CPC {avg_after:.2f} vs LTV {ltv:.2f}."
                    )
                log_with_dfid(
                    logger,
                    dfid,
                    logging.INFO,
                    "Bid %.2f USD - DIM accepts (< %.2f hard limit) -%s",
                    bid,
                    max_cpc,
                    m_note,
                )
                step.console_note = "early_sample"

            if (
                not logged_roi_positive_window
                and avg_after is not None
                and step.roi_estimate_after is not None
                and step.roi_estimate_after > 0
            ):
                logged_roi_positive_window = True
                log_with_dfid(
                    logger,
                    dfid,
                    logging.INFO,
                    "Bid %.2f USD - DIM accepts - ROI positive (LTV %.2f > avg CPC %.2f)",
                    bid,
                    ltv,
                    avg_after,
                )

            if not logged_late and avg_after is not None and avg_after > ltv + 1e-9:
                logged_late = True
                log_with_dfid(
                    logger,
                    dfid,
                    logging.INFO,
                    "Bid %.2f USD - DIM accepts - ROI negative (avg CPC %.2f > LTV %.2f)",
                    bid,
                    avg_after,
                    ltv,
                )
                step.console_note = "late_sample"

            result.steps.append(step)

            if stop:
                result.stopped_reason = "roi_environmental_monitor"
                result.suspension_decision_number = i + 1
                log_with_dfid(
                    logger,
                    dfid,
                    logging.WARNING,
                    "Agent %s -> SUSPENDED (%s)",
                    agent_id,
                    cfg.monitor.suspension_reason,
                )
                break

    if not result.stopped_reason and result.steps:
        result.stopped_reason = "completed_all_inputs"

    record_simulation_end(
        audit,
        sim_id,
        status="ok",
        stopped_reason=result.stopped_reason,
        details={"steps_recorded": len(result.steps)},
        elapsed_seconds=time.perf_counter() - t0,
    )

    return result
