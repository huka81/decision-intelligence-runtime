"""
Orchestrator: market JSON, market_snapshots (kernel), simulated bids, DIM, BusinessROIMonitor.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dir_core import ContextStore, PolicyProposal, new_dfid
from dir_core.agent_registry import AgentRegistry
from dir_core.models import ContextSnapshot

from audit_store import AuditStore
from bidding_dim import validate_cpc_bid_proposal
from models import BiddingSampleConfig
from roi_monitor import BusinessROIMonitor

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


def rolling_avg_cpc_series(audit: AuditStore, window: int) -> List[Optional[float]]:
    """Rolling average CPC after each execution (None until ``window`` executions)."""
    rows = audit.list_executions_chronological()
    series: List[Optional[float]] = []
    for k in range(len(rows)):
        if k + 1 < window:
            series.append(None)
            continue
        lo = k + 1 - window
        sub = rows[lo : k + 1]
        series.append(sum(float(r["cpc_bid_usd"]) for r in sub) / float(window))
    return series


def run_simulation(
    cfg: BiddingSampleConfig,
    *,
    sample_dir: Path,
    audit: AuditStore,
    context_store: ContextStore,
    monitor: BusinessROIMonitor,
    agent_registry: AgentRegistry,
) -> SimulationResult:
    cycles = load_all_cycles(sample_dir, cfg.paths.inputs_file)
    n = len(cycles)
    result = SimulationResult(total_inputs=n)

    ctx_dim = {"state": dict(cfg.dim.context_state)}
    agent_id = cfg.agent.agent_id
    max_cpc = cfg.contract.max_cpc_usd
    margin = cfg.simulation.bid_margin_above_market
    allowed = cfg.dim.allowed_agents or [agent_id]
    ltv = cfg.monitor.ltv_usd

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

        audit.insert_decision_flow(dfid, agent_id, input_ref=cref)

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
        audit.insert_market_snapshot(
            dfid,
            snapshot.snapshot_id,
            market,
            details={
                "search_term": cyc.search_term,
                "cycle_id": cref,
                "campaign_id": cyc.campaign_id,
            },
        )

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

        audit.record(
            dfid,
            "CONTEXT_COMPILED",
            state="READY",
            details={
                "cycle_id": cref,
                "market_cpc_to_win": market,
                "snapshot_id": snapshot.snapshot_id,
            },
        )

        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=agent_id,
            policy_kind="cpc_bid",
            params={"cpc_bid_usd": bid},
            context_ref=snapshot.snapshot_id,
            confidence=0.94,
            justification=(
                f"Simulated bid (cycle {i + 1}/{n}): stay just above market to hold top 3."
            ),
        )

        audit.record(
            dfid,
            "POLICY_PROPOSAL",
            state="EMITTED",
            details={"cpc_bid_usd": bid, "policy_kind": proposal.policy_kind},
        )

        verdict, reason = validate_cpc_bid_proposal(
            proposal,
            ctx_dim,
            allowed,
            max_cpc,
        )

        audit.record(
            dfid,
            "DIM_VALIDATION",
            state=verdict,
            details={"reason": reason},
        )

        step = SimulationStep(
            iteration=i,
            dfid=dfid,
            cycle_id=cref,
            search_term=cyc.search_term,
            market_cpc_to_win=market,
            bid_usd=bid,
            dim_verdict=verdict,
            dim_reason=reason,
            executed=False,
        )

        if verdict != "ACCEPT":
            audit.complete_flow(dfid, status="ABORTED")
            step.console_note = "DIM_REJECT"
            result.steps.append(step)
            continue

        exec_details = {
            "policy_kind": proposal.policy_kind,
            "proposal": proposal.model_dump(mode="json"),
        }
        audit.insert_execution(dfid, bid, details=exec_details)
        audit.record(
            dfid,
            "EXECUTION_LOGGED",
            state="COMPLETED",
            details={"cpc_bid_usd": bid},
        )
        audit.complete_flow(dfid, status="COMPLETED")
        step.executed = True

        stop, avg_after = monitor.evaluate_after_execution(dfid)
        step.rolling_avg_cpc_after = avg_after
        if avg_after is not None:
            step.roi_estimate_after = ltv - avg_after

        if not logged_early and i == 0:
            logged_early = True
            m_note = (
                " Monitor OK (window not full)."
                if avg_after is None
                else f" ROI positive (LTV {ltv:.2f} > avg CPC {avg_after:.2f}) - Monitor OK."
            )
            print(
                f"[decision {i + 1}/{n}] Bid {bid:.2f} USD - DIM Accepts (< {max_cpc:.2f} hard limit) -"
                f"{m_note}"
            )
            step.console_note = "early_sample"

        if (
            not logged_roi_positive_window
            and avg_after is not None
            and step.roi_estimate_after is not None
            and step.roi_estimate_after > 0
        ):
            logged_roi_positive_window = True
            print(
                f"[decision {i + 1}/{n}] Bid {bid:.2f} USD - DIM Accepts (< {max_cpc:.2f} hard limit) - "
                f"ROI positive (LTV {ltv:.2f} > avg CPC {avg_after:.2f}) - Monitor OK"
            )

        if (
            not logged_late
            and avg_after is not None
            and avg_after > ltv + 1e-9
        ):
            logged_late = True
            print(
                f"[decision {i + 1}/{n}] Bid {bid:.2f} USD - DIM Accepts (bid < {max_cpc:.2f} hard limit) - "
                f"ROI becomes negative (avg CPC {avg_after:.2f} > LTV {ltv:.2f})"
            )
            step.console_note = "late_sample"

        result.steps.append(step)

        if stop:
            result.stopped_reason = "roi_environmental_monitor"
            result.suspension_decision_number = i + 1
            print(
                f"Agent state transition: {agent_id} -> SUSPENDED "
                f"(reason: {cfg.monitor.suspension_reason})"
            )
            break

    if not result.stopped_reason and result.steps:
        result.stopped_reason = "completed_all_inputs"

    return result

