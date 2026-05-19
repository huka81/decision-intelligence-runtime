"""
Email ingestion orchestrator: DFID, kernel gates, ROA, DIM, mock bind, canonical audit.

One markdown email = one DecisionFlow. Expects ``AgentRegistry.handshake`` in ``run.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dir_core import AgentRegistry, ContextStore, new_dfid
from dir_core.storage import AuditStore, StorageBundle
from dir_core.utils.logging_utils import log_with_dfid
from email_fixture_ingest import (
    client_application_from_fixture,
    list_markdown_fixtures,
    load_markdown_email_fixture,
)
from gates import run_post_extraction_gates, run_pre_agent_gates
from kernel import DecisionIntegrityModule, DecisionLedger
from policy_binding import PolicyBindingClient
from schemas import ClientApplication, UnderwritingContract

from agent import DecisionCycleReport, ROAUnderwriterAgent
from telemetry import record_underwriting_step

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class EmailCaseResult:
    dfid: str
    source_file: str
    mail_subject: str
    final_status: str
    reason_code: str
    lifecycle_state: str
    dim_result: Optional[str] = None
    policy_ref: Optional[str] = None
    report: Optional[DecisionCycleReport] = None
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    mail_body_markdown: str = ""
    extracted_broker_tiv_usd: Optional[float] = None
    stated_territories_extracted: Optional[str] = None

    def add_step(self, step: str, state: str, detail: str = "") -> None:
        self.timeline.append(
            {
                "step": step,
                "state": state,
                "detail": detail,
                "at": _utc_iso(),
            }
        )


def process_email_file(
    path: Path,
    *,
    contract_dict: Dict[str, Any],
    registry: AgentRegistry,
    context_store: ContextStore,
    dim: DecisionIntegrityModule,
    agent: ROAUnderwriterAgent,
    binder: PolicyBindingClient,
    audit: AuditStore,
    config: Dict[str, Any],
    simulation_id: str,
) -> EmailCaseResult:
    dfid = new_dfid()
    ep = config.get("email_processing", {})
    fx = {k.upper(): float(v) for k, v in ep.get("currency_fx_to_usd", {}).items()}
    agent_id = str(contract_dict["agent_id"])

    def _rec(
        event: str,
        *,
        step_id: str = "",
        state: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            event,
            step_id=step_id,
            state=state,
            details=details,
            agent_id=agent_id,
        )

    log_with_dfid(logger, dfid, logging.INFO, "FLOW_CREATED file=%s", path.name)
    _rec(
        "FLOW_CREATED",
        step_id="0",
        state="CREATED",
        details={"file": path.name},
    )

    fixture = load_markdown_email_fixture(path)
    context = client_application_from_fixture(fixture, fx)

    context_store.update_session(
        dfid, context.model_dump(), agent_id=contract_dict["agent_id"]
    )

    result = EmailCaseResult(
        dfid=dfid,
        source_file=path.name,
        mail_subject=context.mail_subject or path.stem,
        final_status="REJECTED",
        reason_code="UNKNOWN",
        lifecycle_state="ABORTED",
        mail_body_markdown=fixture.body_text,
    )
    result.add_step("MAIL_INGESTED", "CREATED", f"Read {path.name}")
    _rec(
        "MAIL_INGESTED",
        state="CREATED",
        details={
            "subject": context.mail_subject,
            "mail_body_sha256": context.mail_body_sha256,
            "file": path.name,
        },
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "MAIL_INGESTED file=%s mail_body_sha256=%s",
        path.name,
        context.mail_body_sha256,
    )

    result.add_step("CONTEXT_COMPILED", "ACTIVE", "ClientApplication built from email")
    _rec(
        "CONTEXT_COMPILED",
        state="ACTIVE",
        details={
            "requested_tiv_usd": None,
            "note": "TiV from agent extraction, not regex parser",
            "industry_snippet": (context.industry or "")[:120],
        },
    )
    log_with_dfid(logger, dfid, logging.INFO, "CONTEXT_COMPILED")

    gate = run_pre_agent_gates(
        fixture.body_text,
        context,
        UnderwritingContract.model_validate(contract_dict),
        config,
    )
    if gate is not None:
        result.reason_code = gate.code
        result.lifecycle_state = gate.lifecycle_state
        result.final_status = "ESCALATED" if gate.lifecycle_state == "ESCALATED" else "REJECTED"
        ev = (
            "GATE_AUTHORITY_ESCALATED"
            if gate.code == "AUTHORITY_CEILING"
            else "GATE_REJECTED"
        )
        result.add_step(ev, gate.lifecycle_state, gate.message)
        _rec(
            ev,
            state=gate.lifecycle_state,
            details={"code": gate.code, "message": gate.message},
        )
        log_with_dfid(logger, dfid, logging.INFO, "%s code=%s", ev, gate.code)
        _rec(
            "FLOW_TERMINAL",
            state=gate.lifecycle_state,
            details={"outcome": result.final_status},
        )
        return result

    result.add_step(
        "KERNEL_GATES_PASSED",
        "ACTIVE",
        "No optional keyword injection match (territory + authority after agent extraction)",
    )
    _rec(
        "KERNEL_GATES_PASSED",
        state="ACTIVE",
        details={},
    )
    log_with_dfid(logger, dfid, logging.INFO, "KERNEL_GATES_PASSED")

    try:
        facts = agent.extract_submission_facts(dfid, fixture.body_text, fx)
    except (ValueError, TypeError) as exc:
        result.reason_code = "EXTRACTION_FAILED"
        result.lifecycle_state = "ABORTED"
        result.final_status = "REJECTED"
        msg = f"Agent could not extract submission facts: {exc}"
        result.add_step("AGENT_SUBMISSION_EXTRACTION", "ABORTED", msg)
        _rec(
            "AGENT_SUBMISSION_EXTRACTION_FAILED",
            state="ABORTED",
            details={"error": str(exc)},
        )
        log_with_dfid(
            logger,
            dfid,
            logging.WARNING,
            "AGENT_SUBMISSION_EXTRACTION_FAILED: %s",
            exc,
        )
        _rec(
            "FLOW_TERMINAL",
            state="ABORTED",
            details={"outcome": "REJECTED"},
        )
        return result

    result.extracted_broker_tiv_usd = facts.broker_requested_tiv_usd
    result.stated_territories_extracted = facts.stated_territories
    context = context.model_copy(
        update={"requested_tiv_usd": facts.broker_requested_tiv_usd}
    )
    context_store.update_session(
        dfid, context.model_dump(), agent_id=contract_dict["agent_id"]
    )

    detail_lim = f"tiv_usd={facts.broker_requested_tiv_usd:,.0f}"
    detail_ter = (facts.stated_territories or "")[:500]
    result.add_step(
        "AGENT_SUBMISSION_EXTRACTION",
        "ACTIVE",
        f"{detail_lim}; stated_territories: {detail_ter[:200]}{'...' if len(detail_ter) > 200 else ''}",
    )
    _rec(
        "AGENT_SUBMISSION_EXTRACTION",
        state="ACTIVE",
        details={
            "broker_requested_tiv_usd": facts.broker_requested_tiv_usd,
            "stated_territories": facts.stated_territories,
        },
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "AGENT_SUBMISSION_EXTRACTION broker_requested_tiv_usd=%s",
        facts.broker_requested_tiv_usd,
    )

    post = run_post_extraction_gates(
        context,
        facts.stated_territories,
        UnderwritingContract.model_validate(contract_dict),
        config,
    )
    if post is not None:
        result.reason_code = post.code
        result.lifecycle_state = post.lifecycle_state
        result.final_status = (
            "ESCALATED" if post.lifecycle_state == "ESCALATED" else "REJECTED"
        )
        ev = (
            "GATE_AUTHORITY_ESCALATED"
            if post.code == "AUTHORITY_CEILING"
            else "GATE_REJECTED"
        )
        result.add_step(ev, post.lifecycle_state, post.message)
        _rec(
            ev,
            state=post.lifecycle_state,
            details={"code": post.code, "message": post.message},
        )
        log_with_dfid(logger, dfid, logging.INFO, "%s code=%s", ev, post.code)
        _rec(
            "FLOW_TERMINAL",
            state=post.lifecycle_state,
            details={"outcome": result.final_status},
        )
        return result

    result.add_step("AGENT_DECISION_CYCLE", "ACTIVE", "Explain -> Policy -> Self-Check -> PCI")
    pci, report = agent.run_decision_cycle(context, dfid=dfid)
    result.report = report
    _rec(
        "PCI_EMITTED",
        state="VALIDATING",
        details={
            "total_insured_value": report.policy_proposal.total_insured_value,
            "premium": report.policy_proposal.premium,
            "self_check_passed": report.self_check_passed,
        },
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "PCI_EMITTED total_insured_value=%.0f",
        report.policy_proposal.total_insured_value,
    )

    result.add_step("DIM_VERIFY_AND_COMMIT", "VALIDATING", "Proof check + business rules")
    dim_out = dim.verify_and_commit(pci, contract_dict["agent_id"])
    result.dim_result = dim_out
    _rec(
        "DIM_RESULT",
        state="VALIDATING",
        details={"result": dim_out},
    )
    log_with_dfid(logger, dfid, logging.INFO, "DIM_RESULT %s", dim_out)

    if dim_out != "Policy Bound":
        result.final_status = "REJECTED"
        result.reason_code = dim_out.replace(" ", "_").upper()
        result.lifecycle_state = "ABORTED"
        result.add_step("FLOW_ABORTED", "ABORTED", dim_out)
        _rec(
            "FLOW_ABORTED",
            state="ABORTED",
            details={"reason": dim_out},
        )
        log_with_dfid(logger, dfid, logging.WARNING, "FLOW_ABORTED reason=%s", dim_out)
        _rec(
            "FLOW_TERMINAL",
            state="ABORTED",
            details={"outcome": "REJECTED"},
        )
        return result

    result.add_step("LEDGER_COMMITTED", "ACCEPTED", "PCI appended to Decision Ledger")
    _rec(
        "LEDGER_COMMITTED",
        state="ACCEPTED",
        details={},
    )
    log_with_dfid(logger, dfid, logging.INFO, "LEDGER_COMMITTED")

    result.add_step("BIND_API", "EXECUTING", "Mock policy bind")
    br = binder.bind_policy(
        dfid,
        simulation_id=simulation_id,
        total_insured_value=report.policy_proposal.total_insured_value,
        premium=report.policy_proposal.premium,
        industry=report.policy_proposal.industry,
    )
    result.policy_ref = br.policy_ref
    result.final_status = "BOUND"
    result.reason_code = "POLICY_BOUND"
    result.lifecycle_state = "CLOSED"
    result.add_step("BIND_SUCCEEDED", "CLOSED", br.message)
    _rec(
        "FLOW_TERMINAL",
        state="CLOSED",
        details={"outcome": "BOUND", "policy_ref": br.policy_ref},
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "FLOW_TERMINAL outcome=BOUND policy_ref=%s",
        br.policy_ref,
    )
    return result


def run_email_pipeline(
    sample_dir: Path,
    config: Dict[str, Any],
    llm: Any,
    bundle: StorageBundle,
    *,
    registry: AgentRegistry,
    audit: AuditStore,
    simulation_id: str,
    context_store: ContextStore | None = None,
) -> tuple[List[EmailCaseResult], DecisionLedger]:
    binder = PolicyBindingClient(audit)

    contract = _contract_from_config(config)
    contract_dict = contract.model_dump()
    agent_id = contract_dict["agent_id"]

    if context_store is None:
        context_store = ContextStore(storage=bundle.context)
    ledger = DecisionLedger()
    dim = DecisionIntegrityModule(registry, context_store, ledger)
    agent = ROAUnderwriterAgent(registry, agent_id, llm)

    ep = config.get("email_processing", {})
    emails_dir = sample_dir / ep.get("emails_dir", "emails")
    paths = list_markdown_fixtures(emails_dir)

    results: List[EmailCaseResult] = []
    for path in paths:
        results.append(
            process_email_file(
                path,
                contract_dict=contract_dict,
                registry=registry,
                context_store=context_store,
                dim=dim,
                agent=agent,
                binder=binder,
                audit=audit,
                config=config,
                simulation_id=simulation_id,
            )
        )
    return results, ledger


def _contract_from_config(config: Dict[str, Any]) -> UnderwritingContract:
    uw = config.get("underwriting", {})
    agents = config.get("agents", [])
    agent_cfg = agents[0] if agents else {}
    contract_cfg = agent_cfg.get("contract", {})
    return UnderwritingContract(
        agent_id=agent_cfg.get("agent_id", "underwriter_agent"),
        version=agent_cfg.get("version", "1.0.0"),
        created_by=agent_cfg.get("created_by"),
        created_at=agent_cfg.get("created_at"),
        mission=contract_cfg.get("mission")
        or agent_cfg.get("mission", "Underwrite insurance policies."),
        max_tiv=contract_cfg.get("max_tiv", uw.get("max_tiv", 2_000_000)),
        prohibited_industries=contract_cfg.get(
            "prohibited_industries",
            uw.get("prohibited_industries", ["Fireworks", "CryptoMining"]),
        ),
    )
