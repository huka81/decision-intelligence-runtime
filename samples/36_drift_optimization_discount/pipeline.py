"""
Orchestrator: ingest cancellations, ContextStore session, ROA (Explain → Policy → Self-Check),
DIM, canonical telemetry, profitability monitor.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dir_core import ContextStore, PolicyProposal, idempotency_key, new_dfid
from dir_core.agent_registry import AgentRegistry
from dir_core.data_types import ValidationVerdict
from dir_core.models import ResponsibilityContract
from dir_core.storage import StorageBundle
from dir_core.utils.llm_client import LLMClient
from dir_core.utils.logging_utils import log_with_dfid

from dim import validate_retention_proposal
from performance_monitor import PerformanceMonitor
from schemas import RetentionSampleConfig  # type: ignore[attr-defined]
from telemetry import (
    record_agent_decision_summary,
    record_context_compiled,
    record_dim_validation,
    record_policy_proposal,
    record_retention_executed,
)

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _stable_unit_noise(iteration: int, seed: int) -> float:
    h = hash((seed, iteration, 0x9E3779B9)) & 0x7FFFFFFF
    return (h / 0x7FFFFFFF) * 2.0 - 1.0


def simulated_discount_pct(
    index: int,
    total: int,
    cfg: RetentionSampleConfig,
) -> float:
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


def run_retention_roa_cycle(
    llm: LLMClient,
    rc: ResponsibilityContract,
    *,
    row: Dict[str, Any],
    iteration: int,
    total: int,
    dfid: str,
    discount_hint: float,
    agent_id: str,
) -> Tuple[Optional[PolicyProposal], str, str]:
    """Explain → Policy → Self-Check; returns ``(proposal_or_none, narrative, fail_reason)``."""
    mission = rc.mission or "Retain subscribers who request cancellation."
    explain_prompt = (
        f"PHASE=explain\nDFID={dfid}\nITER={iteration + 1}/{total}\n"
        f"DISCOUNT_HINT={discount_hint:.6f}\nINPUT_JSON={json.dumps(row, default=str)}"
    )
    explain_raw = llm.generate(explain_prompt, system=mission)
    ex_obj = parse_llm_json(explain_raw) or {}
    narrative = str(ex_obj.get("narrative") or explain_raw.strip()[:800])

    policy_prompt = (
        f"PHASE=policy\nDFID={dfid}\nITER={iteration + 1}/{total}\n"
        f"DISCOUNT_HINT={discount_hint:.6f}\nEXPLAIN_JSON={json.dumps(ex_obj, default=str)}"
    )
    policy_raw = llm.generate(policy_prompt, system=mission)
    pol = parse_llm_json(policy_raw)
    if not pol:
        return None, narrative, "policy_json_parse_failed"

    policy_kind = str(pol.get("policy_kind") or "")
    params = pol.get("params") if isinstance(pol.get("params"), dict) else {}
    try:
        confidence = float(pol.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    justification = str(pol.get("justification") or "")

    allowed = list(rc.allowed_policy_types or [])
    if policy_kind not in allowed:
        return None, narrative, "self_check_policy_kind"
    if confidence < float(rc.escalate_on_uncertainty):
        return None, narrative, "self_check_confidence"

    raw_disc = params.get("discount_offered", discount_hint)
    try:
        discount_f = float(raw_disc)
    except (TypeError, ValueError):
        return None, narrative, "self_check_discount_type"

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=agent_id,
        policy_kind=policy_kind,
        params={"discount_offered": discount_f},
        confidence=confidence,
        justification=justification,
    )
    return proposal, narrative, ""


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
    explain_narrative: str = ""
    justification: str = ""


@dataclass
class SimulationResult:
    steps: List[SimulationStep] = field(default_factory=list)
    stopped_reason: str = ""
    total_inputs: int = 0
    suspension_decision_number: Optional[int] = None


def _verdict_str(verdict: Any) -> str:
    return verdict.value if hasattr(verdict, "value") else str(verdict)


def run_simulation(
    cfg: RetentionSampleConfig,
    *,
    sample_dir: Path,
    bundle: StorageBundle,
    context_store: ContextStore,
    monitor: PerformanceMonitor,
    agent_registry: AgentRegistry,
    llm: LLMClient,
    rc: ResponsibilityContract,
    simulation_id: str,
) -> SimulationResult:
    inputs_path = sample_dir / cfg.paths.inputs_file
    if not inputs_path.exists():
        raise FileNotFoundError(f"Inputs not found: {inputs_path}")

    rows = load_cancellation_inputs(inputs_path)
    n = len(rows)
    result = SimulationResult(total_inputs=n)

    ctx_dim: Dict[str, Any] = {"state": dict(cfg.dim.context_state)}
    agent_id = cfg.agent.agent_id
    max_disc = cfg.contract.max_discount_pct
    kernel_contract = rc.model_dump()

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

        discount_hint = simulated_discount_pct(i, n, cfg)

        context_store.update_session(
            dfid,
            {
                "cancellation": row,
                "compiled_for": agent_id,
            },
        )

        sess = context_store.get_session(dfid) or {}
        record_context_compiled(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            input_ref=ref,
            session_keys=list(sess.keys()),
            plan=plan,
            channel=channel,
            user_reason=user_reason,
        )

        proposal, narrative, roa_fail = run_retention_roa_cycle(
            llm,
            rc,
            row=row,
            iteration=i,
            total=n,
            dfid=dfid,
            discount_hint=discount_hint,
            agent_id=agent_id,
        )

        discount_for_step = discount_hint
        if proposal is not None:
            try:
                discount_for_step = float(proposal.params.get("discount_offered", discount_hint))
            except (TypeError, ValueError):
                discount_for_step = discount_hint

        step = SimulationStep(
            iteration=i,
            dfid=dfid,
            input_ref=ref,
            plan=plan,
            user_reason=user_reason,
            channel=channel,
            discount_offered=discount_for_step,
            dim_verdict="",
            dim_reason="",
            executed=False,
            explain_narrative=narrative,
            justification=(proposal.justification if proposal else ""),
        )

        if proposal is None:
            step.dim_verdict = "ROA_FAIL"
            step.dim_reason = roa_fail
            log_with_dfid(
                logger,
                dfid,
                logging.WARNING,
                "ROA self-check failed: %s",
                roa_fail,
            )
            record_agent_decision_summary(
                bundle,
                dfid,
                simulation_id,
                agent_id=agent_id,
                policy_kind="",
                verdict="ROA_FAIL",
                reason=roa_fail,
                confidence=0.0,
                justification="",
                explain_narrative=narrative,
            )
            result.steps.append(step)
            continue

        record_policy_proposal(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            discount_offered=float(proposal.params.get("discount_offered", 0.0)),
            policy_kind=proposal.policy_kind,
        )

        verdict, reason = validate_retention_proposal(
            proposal,
            ctx_dim,
            cfg.dim.allowed_agents or [agent_id],
            max_disc,
            kernel_contract=kernel_contract,
        )
        v_str = _verdict_str(verdict)
        step.dim_verdict = v_str
        step.dim_reason = str(reason)

        record_dim_validation(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            verdict=v_str,
            reason=str(reason),
        )

        record_agent_decision_summary(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            policy_kind=proposal.policy_kind,
            verdict=v_str,
            reason=str(reason),
            confidence=proposal.confidence,
            justification=proposal.justification,
            explain_narrative=narrative,
        )

        if verdict != ValidationVerdict.ACCEPT:
            step.console_note = "DIM_REJECT"
            result.steps.append(step)
            continue

        ikey = idempotency_key(
            dfid,
            "retention_discount_apply",
            {"discount": float(discount_for_step)},
        )
        if bundle.idempotency.get(ikey) is not None:
            step.console_note = "idempotency_skip"
            result.steps.append(step)
            continue

        bundle.idempotency.set(
            ikey,
            {"dfid": dfid, "discount_offered": float(discount_for_step)},
        )

        record_retention_executed(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            discount_offered=float(discount_for_step),
            policy_kind=proposal.policy_kind,
            proposal_dump=proposal.model_dump(mode="json"),
        )
        step.executed = True

        stop, mavg = monitor.evaluate_after_execution(dfid)
        step.moving_avg_after = mavg

        if not logged_early and i == 0:
            logged_early = True
            m_note = (
                " Monitor OK (window not full)."
                if mavg is None
                else f" Moving avg {mavg:.1f}% - Monitor OK."
            )
            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "decision %s/%s discount=%.1f%% - DIM Accepts -%s",
                i + 1,
                n,
                discount_for_step,
                m_note,
            )
            step.console_note = "early_sample"

        if not logged_late and discount_for_step >= 10.5:
            logged_late = True
            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "decision %s/%s discount=%.1f%% - DIM Accepts (under %.0f%% cap only; "
                "profitability not enforced by DIM). Trajectory approaches ~%.1f%% by end.",
                i + 1,
                n,
                discount_for_step,
                max_disc,
                cfg.simulation.drift_discount_end,
            )
            step.console_note = "late_sample"

        result.steps.append(step)

        if stop:
            result.stopped_reason = "profitability_drift_monitor"
            result.suspension_decision_number = i + 1
            log_with_dfid(
                logger,
                dfid,
                logging.WARNING,
                "Agent state transition: %s -> SUSPENDED (reason=%s)",
                agent_id,
                cfg.monitor.suspension_reason,
            )
            break

    if not result.stopped_reason and result.steps:
        result.stopped_reason = "completed_all_inputs"

    return result


def moving_average_series(discounts: List[float], window: int) -> List[Optional[float]]:
    """Rolling average after each executed discount index (``None`` until window full)."""
    series: List[Optional[float]] = []
    for k in range(len(discounts)):
        if k + 1 < window:
            series.append(None)
            continue
        start = k + 1 - window
        slice_rows = discounts[start:k + 1]
        avg = sum(slice_rows) / window
        series.append(avg)
    return series
