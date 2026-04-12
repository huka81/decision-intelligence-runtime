"""
Orchestrator: ingest cancellations, ContextStore session, simulated agent, DIM, audit, monitor.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dir_core import ContextStore, PolicyProposal, new_dfid
from dir_core.agent_registry import AgentRegistry

from audit_store import AuditStore
from models import RetentionSampleConfig
from performance_monitor import PerformanceMonitor
from retention_dim import validate_retention_proposal

logger = logging.getLogger(__name__)


def _stable_unit_noise(iteration: int, seed: int) -> float:
    """Deterministic value in [-1, 1] for reproducible runs."""
    h = hash((seed, iteration, 0x9E3779B9)) & 0x7FFFFFFF
    return (h / 0x7FFFFFFF) * 2.0 - 1.0


def simulated_discount_pct(
    index: int,
    total: int,
    cfg: RetentionSampleConfig,
) -> float:
    """
    Phase 1 (index < normal_phase_iterations): discount ~N(mean, small spread) — healthy margin band.
    Phase 2: slow upward creep (t**exponent) + slow jitter + faster offer-level volatility.
    A single executed offer may be above the rolling average for many steps; suspension uses
    only the window mean vs monitor threshold (DIM still enforces max_discount_pct).
    """
    sim = cfg.simulation
    max_disc = float(cfg.contract.max_discount_pct)
    k = sim.normal_phase_iterations
    if total <= 1:
        return float(min(max_disc, sim.normal_discount_mean))

    if index < k or k >= total:
        half = sim.normal_discount_peak_to_peak_pct / 2.0
        u = _stable_unit_noise(index, sim.simulation_seed)
        d = sim.normal_discount_mean + half * u
        lo = max(3.0, sim.normal_discount_mean - half * 1.2)
        hi = min(8.5, sim.normal_discount_mean + half * 1.2)
        return float(max(lo, min(min(hi, max_disc), d)))

    span = max((total - 1) - k, 1)
    t = (index - k) / span
    t = min(1.0, max(0.0, t))
    exp = sim.drift_curve_exponent
    s0 = sim.drift_discount_start_phase2
    s1 = sim.drift_discount_end
    base = s0 + (s1 - s0) * (t**exp)
    noise = sim.drift_phase_noise_pp * _stable_unit_noise(
        index, sim.simulation_seed + 0x5F3759DF
    )
    fast = sim.drift_offer_volatility_pp * _stable_unit_noise(
        index, sim.simulation_seed + 0xC001D00D
    )
    d = base + noise + fast
    return float(max(0.0, min(max_disc, d)))


def load_cancellation_inputs(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "cancellations" in data:
            return list(data["cancellations"])
        raise ValueError(
            f"Expected a JSON array or an object with 'cancellations' key: {path}"
        )
    out: List[Dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


@dataclass
class SimulationStep:
    iteration: int
    dfid: str
    input_ref: str
    plan: str
    user_reason: str
    channel: str
    discount_offered: float
    dim_verdict: str
    dim_reason: str
    executed: bool
    moving_avg_after: Optional[float] = None
    console_note: str = ""


@dataclass
class SimulationResult:
    steps: List[SimulationStep] = field(default_factory=list)
    stopped_reason: str = ""
    total_inputs: int = 0
    suspension_decision_number: Optional[int] = None


def run_simulation(
    cfg: RetentionSampleConfig,
    *,
    sample_dir: Path,
    audit: AuditStore,
    context_store: ContextStore,
    monitor: PerformanceMonitor,
    agent_registry: AgentRegistry,
) -> SimulationResult:
    inputs_path = sample_dir / cfg.paths.inputs_file
    if not inputs_path.exists():
        raise FileNotFoundError(f"Inputs not found: {inputs_path}")

    rows = load_cancellation_inputs(inputs_path)
    n = len(rows)
    result = SimulationResult(total_inputs=n)

    ctx_dim = {"state": dict(cfg.dim.context_state)}
    agent_id = cfg.agent.agent_id
    max_disc = cfg.contract.max_discount_pct

    logged_early = False
    logged_late = False

    for i, row in enumerate(rows):
        st = agent_registry.get_agent_status(agent_id)
        if st and st[0] == "SUSPENDED":
            result.stopped_reason = "agent_already_suspended"
            break

        dfid = new_dfid()
        ref = str(row.get("cancellation_id", f"row-{i}"))
        plan = str(row.get("plan", ""))
        user_reason = str(
            row.get("user_reason")
            or row.get("subscriber_message")
            or row.get("reason_text")
            or row.get("reason", "")
        )
        channel = str(row.get("channel", ""))

        audit.insert_decision_flow(dfid, agent_id, input_ref=ref)
        context_store.update_session(
            dfid,
            {
                "cancellation": row,
                "compiled_for": "RetentionAgent",
            },
        )

        discount = simulated_discount_pct(i, n, cfg)

        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=agent_id,
            policy_kind="retention_discount",
            params={"discount_offered": discount},
            confidence=0.95,
            justification=f"Simulated retention offer (iteration {i + 1}/{n}) to reduce churn.",
        )

        audit.record(
            dfid,
            "CONTEXT_COMPILED",
            state="READY",
            details={"input_ref": ref, "session_keys": list(context_store.get_session(dfid).keys())},
        )
        audit.record(
            dfid,
            "POLICY_PROPOSAL",
            state="EMITTED",
            details={"discount_offered": discount, "policy_kind": proposal.policy_kind},
        )

        verdict, reason = validate_retention_proposal(
            proposal,
            ctx_dim,
            cfg.dim.allowed_agents or [agent_id],
            max_disc,
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
            input_ref=ref,
            plan=plan,
            user_reason=user_reason,
            channel=channel,
            discount_offered=discount,
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
        audit.insert_execution(dfid, discount, details=exec_details)
        audit.record(
            dfid,
            "EXECUTION_LOGGED",
            state="COMPLETED",
            details={"discount_offered": discount},
        )
        audit.complete_flow(dfid, status="COMPLETED")
        step.executed = True

        stop, mavg = monitor.evaluate_after_execution(dfid)
        step.moving_avg_after = mavg

        # Console narrative (representative early / late / pre-suspend)
        if not logged_early and i == 0:
            logged_early = True
            m_note = " Monitor OK (window not full)." if mavg is None else f" Moving avg {mavg:.1f}% - Monitor OK."
            print(
                f"[decision {i + 1}/{n}] discount={discount:.1f}% - DIM Accepts -{m_note}"
            )
            step.console_note = "early_sample"

        # Before the monitor fires, show upward creep (run ends when rolling avg trips threshold).
        if not logged_late and discount >= 10.5:
            logged_late = True
            print(
                f"[decision {i + 1}/{n}] discount={discount:.1f}% - DIM Accepts "
                f"(under {max_disc:.0f}% cap only; profitability not enforced by DIM). "
                f"Trajectory would reach ~{cfg.simulation.drift_discount_end:.1f}% by iteration {n}."
            )
            step.console_note = "late_sample"

        result.steps.append(step)

        if stop:
            result.stopped_reason = "profitability_drift_monitor"
            result.suspension_decision_number = i + 1
            if mavg is not None:
                print(f"Alert: Moving average discount is {mavg:.2f}%. Suspending agent.")
            print(
                f"Agent state transition: {agent_id} -> SUSPENDED (reason={cfg.monitor.suspension_reason})"
            )
            break

    if not result.stopped_reason and result.steps:
        result.stopped_reason = "completed_all_inputs"

    return result


def moving_average_series(audit: AuditStore, window: int) -> List[Optional[float]]:
    """For charting: rolling avg after each execution row (None until window full)."""
    rows = audit.list_executions_chronological()
    series: List[Optional[float]] = []
    for k in range(len(rows)):
        if k + 1 < window:
            series.append(None)
            continue
        slice_rows = rows[k + 1 - window : k + 1]
        avg = sum(r["discount_offered"] for r in slice_rows) / window
        series.append(avg)
    return series

