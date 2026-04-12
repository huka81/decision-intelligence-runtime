"""
Orchestrator: ingest support tickets, ContextStore, ContextSnapshot audit, simulated agent, DIM, ComplianceMonitor.
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
from compliance_monitor import ComplianceMonitor
from models import RefundSampleConfig
from refund_dim import validate_refund_proposal

logger = logging.getLogger(__name__)


def load_support_ticket_rows(path: Path) -> List[Dict[str, Any]]:
    """Load tickets from JSON array or ``{ \"tickets\": [...] }`` (same pattern as Sample 36)."""
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
    """
    User Space simulation: after normal_phase_iterations, empathy bias can issue refunds
    under the delay threshold when emotional keywords appear.
    """
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
    audit: AuditStore,
    context_store: ContextStore,
    monitor: ComplianceMonitor,
    agent_registry: AgentRegistry,
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

        audit.insert_decision_flow(dfid, agent_id, input_ref=ref)

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
        audit.insert_context_snapshot(
            dfid,
            snapshot.snapshot_id,
            ticket.delay_hours,
            details={
                "subject": ticket.subject,
                "ticket_id": ref,
                "order_ref": ticket.order_ref,
                "channel": ticket.channel,
            },
        )

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

        audit.record(
            dfid,
            "CONTEXT_COMPILED",
            state="READY",
            details={
                "input_ref": ref,
                "delay_hours": ticket.delay_hours,
                "snapshot_id": snapshot.snapshot_id,
            },
        )

        preview = ticket.body.replace("\n", " ").strip()[:120]

        if refund_eur is None:
            audit.record(
                dfid,
                "NO_REFUND_PROPOSAL",
                state="SKIPPED",
                details={"reason": "Simulated agent declined refund for this ticket"},
            )
            audit.complete_flow(dfid, status="COMPLETED")
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

        audit.record(
            dfid,
            "POLICY_PROPOSAL",
            state="EMITTED",
            details={
                "refund_amount_eur": refund_eur,
                "policy_kind": proposal.policy_kind,
            },
        )

        verdict, reason = validate_refund_proposal(
            proposal,
            ctx_dim,
            cfg.dim.allowed_agents or [agent_id],
            max_refund,
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
            order_ref=ticket.order_ref,
            channel=ticket.channel,
            delay_hours=ticket.delay_hours,
            subject=ticket.subject,
            message_preview=preview,
            refund_amount_eur=refund_eur,
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
        audit.insert_execution(dfid, refund_eur, details=exec_details)
        audit.record(
            dfid,
            "EXECUTION_LOGGED",
            state="COMPLETED",
            details={"refund_amount_eur": refund_eur},
        )
        audit.complete_flow(dfid, status="COMPLETED")
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
            print(
                f"[decision {i + 1}/{n}] delay={ticket.delay_hours:.0f}h refund={refund_eur:.0f} EUR "
                f"- DIM Accepts -{m_note}"
            )
            step.console_note = "early_sample"

        if (
            not logged_late
            and refund_eur is not None
            and ticket.delay_hours <= cfg.monitor.min_delay_hours_for_refund + 1e-9
        ):
            logged_late = True
            print(
                f"[decision {i + 1}/{n}] delay={ticket.delay_hours:.0f}h refund={refund_eur:.0f} EUR "
                f"- DIM Accepts (under {max_refund:.0f} EUR cap only; 48h semantic rule not enforced by DIM)."
            )
            step.console_note = "late_sample"

        result.steps.append(step)

        if stop:
            result.stopped_reason = "semantic_compliance_monitor"
            result.suspension_decision_number = i + 1
            print(
                f"Agent state transition: {agent_id} -> SUSPENDED (reason={cfg.monitor.suspension_reason})"
            )
            break

    if not result.stopped_reason and result.steps:
        result.stopped_reason = "completed_all_inputs"

    return result


def rolling_violation_series(
    audit: AuditStore,
    window: int,
    *,
    min_delay_hours_exclusive: float,
) -> List[Optional[float]]:
    """Rolling violation rate after each execution row (None until window full)."""
    rows = audit.list_executions_chronological()
    series: List[Optional[float]] = []
    for k in range(len(rows)):
        if k + 1 < window:
            series.append(None)
            continue
        # Mirror global last-window semantics on prefix 0..k of chronological rows.
        lo = k + 1 - window
        sub = rows[lo:k + 1]
        viol = sum(
            1
            for r in sub
            if float(r["delay_hours"]) <= min_delay_hours_exclusive + 1e-9
        )
        series.append(viol / float(window))
    return series

