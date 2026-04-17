"""
Orchestrator: ingest support tickets, ContextStore, simulated agent, DIM, ComplianceMonitor.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dir_core import ContextStore, PolicyProposal, idempotency_key, new_dfid
from dir_core.agent_registry import AgentRegistry
from dir_core.data_types import ValidationVerdict
from dir_core.models import ContextSnapshot
from dir_core.storage import StorageBundle
from dir_core.utils.logging_utils import log_with_dfid

from compliance_monitor import ComplianceMonitor
from dim import validate_refund_proposal
from schemas import RefundSampleConfig
from telemetry import (
    record_dim_validation,
    record_no_refund_proposal,
    record_policy_proposal,
    record_refund_context_compiled,
    record_refund_executed,
)

logger = logging.getLogger(__name__)


def load_support_ticket_rows(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "tickets" in data:
        return list(data["tickets"])
    raise ValueError(
        f"Expected a JSON array or an object with 'tickets' key: {path}"
    )


@dataclass
class TicketRecord:
    ticket_id: str
    delay_hours: float
    subject: str
    body: str
    order_ref: str = ""
    channel: str = ""
    carrier: str = ""
    customer_id: str = ""


def ticket_row_to_record(row: Dict[str, Any]) -> TicketRecord:
    msg = (
        row.get("customer_message")
        or row.get("body")
        or row.get("message")
        or row.get("user_reason")
        or ""
    )
    return TicketRecord(
        ticket_id=str(row["ticket_id"]),
        delay_hours=float(row["delay_hours"]),
        subject=str(row.get("subject", "")),
        body=str(msg).strip(),
        order_ref=str(row.get("order_ref", "")),
        channel=str(row.get("channel", "")),
        carrier=str(row.get("carrier", "")),
        customer_id=str(row.get("customer_id", "")),
    )


def load_all_tickets(sample_dir: Path, inputs_file: str) -> List[TicketRecord]:
    path = sample_dir / inputs_file
    if not path.exists():
        raise FileNotFoundError(f"Ticket input file not found: {path}")
    return [ticket_row_to_record(r) for r in load_support_ticket_rows(path)]


def _message_has_emotional_trigger(message: str, keywords: List[str]) -> bool:
    low = message.lower()
    return any(k.lower() in low for k in keywords)


def simulated_refund_eur(
    iteration: int,
    ticket: TicketRecord,
    cfg: RefundSampleConfig,
) -> Optional[float]:
    dh = ticket.delay_hours
    threshold = cfg.monitor.min_delay_hours_for_refund
    compliant = dh > threshold + 1e-9
    emotional = _message_has_emotional_trigger(ticket.body, cfg.simulation.emotional_keywords)

    if iteration < cfg.simulation.normal_phase_iterations:
        if compliant:
            return float(cfg.simulation.refund_amount_compliant_eur)
        return None

    if compliant:
        return float(cfg.simulation.refund_amount_compliant_eur)
    if emotional:
        return float(cfg.simulation.refund_amount_drift_eur)
    return None


def _verdict_str(verdict: ValidationVerdict) -> str:
    return verdict.value if hasattr(verdict, "value") else str(verdict)


@dataclass
class SimulationStep:
    iteration: int
    dfid: str
    input_ref: str
    order_ref: str
    channel: str
    delay_hours: float
    subject: str
    message_preview: str
    refund_amount_eur: Optional[float]
    dim_verdict: str
    dim_reason: str
    executed: bool
    violation_rate_after: Optional[float] = None
    console_note: str = ""


@dataclass
class SimulationResult:
    steps: List[SimulationStep] = field(default_factory=list)
    stopped_reason: str = ""
    total_inputs: int = 0
    suspension_decision_number: Optional[int] = None


def run_simulation(
    cfg: RefundSampleConfig,
    *,
    sample_dir: Path,
    bundle: StorageBundle,
    context_store: ContextStore,
    monitor: ComplianceMonitor,
    agent_registry: AgentRegistry,
    simulation_id: str,
    kernel_contract: Dict[str, Any],
) -> SimulationResult:
    tickets = load_all_tickets(sample_dir, cfg.paths.inputs_file)
    n = len(tickets)
    result = SimulationResult(total_inputs=n)

    ctx_dim = {"state": dict(cfg.dim.context_state)}
    agent_id = cfg.agent.agent_id
    max_refund = cfg.contract.max_refund_eur

    logged_early = False
    logged_late = False

    for i, ticket in enumerate(tickets):
        st = agent_registry.get_agent_status(agent_id)
        if st and st[0] == "SUSPENDED":
            result.stopped_reason = "agent_already_suspended"
            break

        dfid = new_dfid()
        ref = ticket.ticket_id
        refund_eur = simulated_refund_eur(i, ticket, cfg)

        snap_data: dict[str, Any] = {
            "ticket_id": ref,
            "delay_hours": ticket.delay_hours,
            "subject": ticket.subject,
            "order_ref": ticket.order_ref,
            "channel": ticket.channel,
            "carrier": ticket.carrier,
            "compiled_for": agent_id,
        }
        snapshot = ContextSnapshot.create(dfid, snap_data, source="context_compiler")

        context_store.update_session(
            dfid,
            {
                "ticket": {
                    "ticket_id": ref,
                    "customer_id": ticket.customer_id,
                    "delay_hours": ticket.delay_hours,
                    "subject": ticket.subject,
                    "order_ref": ticket.order_ref,
                    "channel": ticket.channel,
                    "carrier": ticket.carrier,
                    "body": ticket.body,
                },
                "snapshot_id": snapshot.snapshot_id,
            },
        )

        preview = ticket.body.replace("\n", " ").strip()[:120]
        record_refund_context_compiled(
            bundle,
            dfid,
            simulation_id,
            input_ref=ref,
            delay_hours=ticket.delay_hours,
            snapshot_id=snapshot.snapshot_id,
            order_ref=ticket.order_ref,
            channel=ticket.channel,
            subject=ticket.subject,
            message_preview=preview,
        )

        if refund_eur is None:
            record_no_refund_proposal(
                bundle,
                dfid,
                simulation_id,
                reason="Simulated agent declined refund for this ticket",
            )
            result.steps.append(
                SimulationStep(
                    iteration=i,
                    dfid=dfid,
                    input_ref=ref,
                    order_ref=ticket.order_ref,
                    channel=ticket.channel,
                    delay_hours=ticket.delay_hours,
                    subject=ticket.subject,
                    message_preview=preview,
                    refund_amount_eur=None,
                    dim_verdict="—",
                    dim_reason="No proposal",
                    executed=False,
                    console_note="no_refund",
                )
            )
            continue

        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=agent_id,
            policy_kind="REFUND",
            params={"refund_amount_eur": refund_eur},
            context_ref=snapshot.snapshot_id,
            confidence=0.92,
            justification=(
                f"Simulated refund proposal (iteration {i + 1}/{n}) for ticket {ref}."
            ),
        )

        record_policy_proposal(
            bundle,
            dfid,
            simulation_id,
            refund_amount_eur=float(refund_eur),
            policy_kind=proposal.policy_kind,
        )

        verdict, reason = validate_refund_proposal(
            proposal,
            ctx_dim,
            cfg.dim.allowed_agents or [agent_id],
            max_refund,
            kernel_contract=kernel_contract,
        )
        v_str = _verdict_str(verdict)

        record_dim_validation(
            bundle,
            dfid,
            simulation_id,
            verdict=v_str,
            reason=str(reason),
        )

        step = SimulationStep(
            iteration=i,
            dfid=dfid,
            input_ref=ref,
            order_ref=ticket.order_ref,
            channel=ticket.channel,
            delay_hours=ticket.delay_hours,
            subject=ticket.subject,
            message_preview=preview,
            refund_amount_eur=refund_eur,
            dim_verdict=v_str,
            dim_reason=str(reason),
            executed=False,
        )

        if verdict != ValidationVerdict.ACCEPT:
            step.console_note = "DIM_REJECT"
            result.steps.append(step)
            continue

        ikey = idempotency_key(
            dfid,
            "refund_execute",
            {"eur": float(refund_eur), "ticket": ref},
        )
        if bundle.idempotency.get(ikey) is not None:
            step.console_note = "idempotency_skip"
            result.steps.append(step)
            continue

        bundle.idempotency.set(
            ikey,
            {"dfid": dfid, "refund_amount_eur": float(refund_eur)},
        )

        record_refund_executed(
            bundle,
            dfid,
            simulation_id,
            refund_amount_eur=float(refund_eur),
            delay_hours=ticket.delay_hours,
            ticket_id=ref,
            order_ref=ticket.order_ref,
            channel=ticket.channel,
            policy_kind=proposal.policy_kind,
            proposal_dump=proposal.model_dump(mode="json"),
        )
        step.executed = True

        stop, vrate = monitor.evaluate_after_execution(dfid)
        step.violation_rate_after = vrate

        if not logged_early and i == 0 and refund_eur is not None:
            logged_early = True
            m_note = (
                " Monitor OK (window not full)."
                if vrate is None
                else f" Semantic violation rate {vrate * 100:.1f}% — Monitor OK."
            )
            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "decision %s/%s delay=%.0fh refund=%.0f EUR - DIM Accepts -%s",
                i + 1,
                n,
                ticket.delay_hours,
                refund_eur,
                m_note,
            )
            step.console_note = "early_sample"

        if (
            not logged_late
            and refund_eur is not None
            and ticket.delay_hours <= cfg.monitor.min_delay_hours_for_refund + 1e-9
        ):
            logged_late = True
            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "decision %s/%s delay=%.0fh refund=%.0f EUR - DIM Accepts "
                "(under %.0f EUR cap only; 48h semantic rule not enforced by DIM).",
                i + 1,
                n,
                ticket.delay_hours,
                refund_eur,
                max_refund,
            )
            step.console_note = "late_sample"

        result.steps.append(step)

        if stop:
            result.stopped_reason = "semantic_compliance_monitor"
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


def rolling_violation_series(
    bundle: StorageBundle,
    simulation_id: str,
    window: int,
    *,
    min_delay_hours_exclusive: float,
) -> List[Optional[float]]:
    delays: List[float] = []
    for row in bundle.decision_audit.all_events_chronological():
        if row.get("event") != "REFUND_EXECUTED":
            continue
        d = row.get("details") or {}
        if d.get("simulation_id") != simulation_id:
            continue
        delays.append(float(d.get("delay_hours", 0.0)))

    series: List[Optional[float]] = []
    for k in range(len(delays)):
        if k + 1 < window:
            series.append(None)
            continue
        lo = k + 1 - window
        sub = delays[lo : k + 1]
        viol = sum(
            1 for dh in sub if float(dh) <= min_delay_hours_exclusive + 1e-9
        )
        series.append(viol / float(window))
    return series
