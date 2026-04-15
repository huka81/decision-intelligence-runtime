"""
Email ingestion orchestrator: DFID, kernel gates, ROA, DIM, mock bind, audit.

One markdown email = one DecisionFlow (DIR §4.2).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dir_core import new_dfid
from dir_core.storage import AuditStore, sqlite_storage
from email_fixture_ingest import (
    client_application_from_fixture,
    list_markdown_fixtures,
    load_markdown_email_fixture,
)
from gates import run_post_extraction_gates, run_pre_agent_gates
from kernel import (
    AgentRegistry,
    ContextStore,
    DecisionIntegrityModule,
    DecisionLedger,
)
from models import ClientApplication, UnderwritingContract
from policy_binding import PolicyBindingClient
from roa_underwriter_agent import DecisionCycleReport, ROAUnderwriterAgent

try:
    from .llm_client import MockLLM, OllamaClient
except ImportError:
    from llm_client import MockLLM, OllamaClient

logger = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def structured_log(dfid: str, event: str, **details: Any) -> None:
    """LG-2: dfid + event + timestamp in one JSON line."""
    payload = {"dfid": dfid, "event": event, "timestamp": _utc_iso(), **details}
    logger.info(json.dumps(payload, default=str))


@dataclass
class EmailCaseResult:
    """One processed email — for console, HTML, and tests."""

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
    # Full fixture text for HTML audit (not written to SQLite audit rows).
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


def _record(
    audit: AuditStore,
    dfid: str,
    event: str,
    *,
    step_id: str = "",
    state: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(dfid, event, step_id=step_id, state=state, details=details or {})


def process_email_file(
    path: Path,
    *,
    contract: UnderwritingContract,
    registry: AgentRegistry,
    dim: DecisionIntegrityModule,
    agent: ROAUnderwriterAgent,
    binder: PolicyBindingClient,
    audit: AuditStore,
    config: Dict[str, Any],
) -> EmailCaseResult:
    dfid = new_dfid()
    ep = config.get("email_processing", {})
    fx = {k.upper(): float(v) for k, v in ep.get("currency_fx_to_usd", {}).items()}

    structured_log(dfid, "FLOW_CREATED", step="orchestrator", file=path.name)
    _record(audit, dfid, "FLOW_CREATED", step_id="0", state="CREATED", details={"file": path.name})

    fixture = load_markdown_email_fixture(path)
    context = client_application_from_fixture(fixture, fx)

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
    _record(
        audit,
        dfid,
        "MAIL_INGESTED",
        state="CREATED",
        details={
            "subject": context.mail_subject,
            "mail_body_sha256": context.mail_body_sha256,
            "file": path.name,
        },
    )
    structured_log(dfid, "MAIL_INGESTED", file=path.name, mail_body_sha256=context.mail_body_sha256)

    result.add_step("CONTEXT_COMPILED", "ACTIVE", "ClientApplication built from email")
    _record(
        audit,
        dfid,
        "CONTEXT_COMPILED",
        state="ACTIVE",
        details={
            "requested_tiv_usd": None,
            "note": "TiV from agent extraction, not regex parser",
            "industry_snippet": (context.industry or "")[:120],
        },
    )
    structured_log(dfid, "CONTEXT_COMPILED", requested_tiv_usd=None)

    gate = run_pre_agent_gates(fixture.body_text, context, contract, config)
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
        _record(
            audit,
            dfid,
            ev,
            state=gate.lifecycle_state,
            details={"code": gate.code, "message": gate.message},
        )
        structured_log(dfid, ev, code=gate.code, state=gate.lifecycle_state)
        _record(audit, dfid, "FLOW_TERMINAL", state=gate.lifecycle_state, details={"outcome": result.final_status})
        return result

    result.add_step(
        "KERNEL_GATES_PASSED",
        "ACTIVE",
        "No optional keyword injection match (territory + authority after agent extraction)",
    )
    _record(audit, dfid, "KERNEL_GATES_PASSED", state="ACTIVE", details={})
    structured_log(dfid, "KERNEL_GATES_PASSED")

    try:
        facts = agent.extract_submission_facts(dfid, fixture.body_text, fx)
    except (ValueError, TypeError) as exc:
        result.reason_code = "EXTRACTION_FAILED"
        result.lifecycle_state = "ABORTED"
        result.final_status = "REJECTED"
        msg = f"Agent could not extract submission facts: {exc}"
        result.add_step("AGENT_SUBMISSION_EXTRACTION", "ABORTED", msg)
        _record(
            audit,
            dfid,
            "AGENT_SUBMISSION_EXTRACTION_FAILED",
            state="ABORTED",
            details={"error": str(exc)},
        )
        structured_log(dfid, "AGENT_SUBMISSION_EXTRACTION_FAILED", error=str(exc))
        _record(
            audit,
            dfid,
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
    detail_lim = f"tiv_usd={facts.broker_requested_tiv_usd:,.0f}"
    detail_ter = (facts.stated_territories or "")[:500]
    result.add_step(
        "AGENT_SUBMISSION_EXTRACTION",
        "ACTIVE",
        f"{detail_lim}; stated_territories: {detail_ter[:200]}{'...' if len(detail_ter) > 200 else ''}",
    )
    _record(
        audit,
        dfid,
        "AGENT_SUBMISSION_EXTRACTION",
        state="ACTIVE",
        details={
            "broker_requested_tiv_usd": facts.broker_requested_tiv_usd,
            "stated_territories": facts.stated_territories,
        },
    )
    structured_log(
        dfid,
        "AGENT_SUBMISSION_EXTRACTION",
        broker_requested_tiv_usd=facts.broker_requested_tiv_usd,
    )

    post = run_post_extraction_gates(
        context, facts.stated_territories, contract, config
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
        _record(
            audit,
            dfid,
            ev,
            state=post.lifecycle_state,
            details={"code": post.code, "message": post.message},
        )
        structured_log(dfid, ev, code=post.code, state=post.lifecycle_state)
        _record(
            audit,
            dfid,
            "FLOW_TERMINAL",
            state=post.lifecycle_state,
            details={"outcome": result.final_status},
        )
        return result

    result.add_step("AGENT_DECISION_CYCLE", "ACTIVE", "Explain -> Policy -> Self-Check -> PCI")
    pci, report = agent.run_decision_cycle(context, dfid=dfid)
    result.report = report
    _record(
        audit,
        dfid,
        "PCI_EMITTED",
        state="VALIDATING",
        details={
            "total_insured_value": report.policy_proposal.total_insured_value,
            "premium": report.policy_proposal.premium,
            "self_check_passed": report.self_check_passed,
        },
    )
    structured_log(
        dfid,
        "PCI_EMITTED",
        total_insured_value=report.policy_proposal.total_insured_value,
    )

    result.add_step("DIM_VERIFY_AND_COMMIT", "VALIDATING", "Proof check + business rules")
    dim_out = dim.verify_and_commit(pci, context)
    result.dim_result = dim_out
    _record(
        audit,
        dfid,
        "DIM_RESULT",
        state="VALIDATING",
        details={"result": dim_out},
    )
    structured_log(dfid, "DIM_RESULT", result=dim_out)

    if dim_out != "Policy Bound":
        result.final_status = "REJECTED"
        result.reason_code = dim_out.replace(" ", "_").upper()
        result.lifecycle_state = "ABORTED"
        result.add_step("FLOW_ABORTED", "ABORTED", dim_out)
        _record(audit, dfid, "FLOW_ABORTED", state="ABORTED", details={"reason": dim_out})
        structured_log(dfid, "FLOW_ABORTED", reason=dim_out)
        _record(audit, dfid, "FLOW_TERMINAL", state="ABORTED", details={"outcome": "REJECTED"})
        return result

    result.add_step("LEDGER_COMMITTED", "ACCEPTED", "PCI appended to Decision Ledger")
    _record(audit, dfid, "LEDGER_COMMITTED", state="ACCEPTED", details={})
    structured_log(dfid, "LEDGER_COMMITTED")

    result.add_step("BIND_API", "EXECUTING", "Mock policy bind")
    br = binder.bind_policy(
        dfid,
        total_insured_value=report.policy_proposal.total_insured_value,
        premium=report.policy_proposal.premium,
        industry=report.policy_proposal.industry,
    )
    result.policy_ref = br.policy_ref
    result.final_status = "BOUND"
    result.reason_code = "POLICY_BOUND"
    result.lifecycle_state = "CLOSED"
    result.add_step("BIND_SUCCEEDED", "CLOSED", br.message)
    _record(
        audit,
        dfid,
        "FLOW_TERMINAL",
        state="CLOSED",
        details={"outcome": "BOUND", "policy_ref": br.policy_ref},
    )
    structured_log(dfid, "FLOW_TERMINAL", outcome="BOUND", policy_ref=br.policy_ref)
    return result


def run_email_pipeline(
    sample_dir: Path,
    config: Dict[str, Any],
    llm: Any,
) -> tuple[List[EmailCaseResult], DecisionLedger, AuditStore]:
    contract = _contract_from_config(config)
    registry = AgentRegistry(contract)
    context_store = ContextStore()
    ledger = DecisionLedger()
    dim = DecisionIntegrityModule(registry, context_store, ledger)
    agent = ROAUnderwriterAgent(registry, llm)

    db_path = sample_dir / config.get("email_processing", {}).get(
        "audit_db", "data/underwriting_audit.sqlite"
    )
    if os.environ.get("UNDERWRITING_AUDIT_DB"):
        db_path = Path(os.environ["UNDERWRITING_AUDIT_DB"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repository = sqlite_storage(str(db_path.resolve()))
    audit = AuditStore(repository.decision_audit, repository.idempotency)
    binder = PolicyBindingClient(audit)

    ep = config.get("email_processing", {})
    emails_dir = sample_dir / ep.get("emails_dir", "emails")
    paths = list_markdown_fixtures(emails_dir)

    results: List[EmailCaseResult] = []
    for path in paths:
        results.append(
            process_email_file(
                path,
                contract=contract,
                registry=registry,
                dim=dim,
                agent=agent,
                binder=binder,
                audit=audit,
                config=config,
            )
        )
    return results, ledger, audit


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
        mission=agent_cfg.get("mission", "Underwrite insurance policies."),
        max_tiv=contract_cfg.get("max_tiv", uw.get("max_tiv", 2_000_000)),
        prohibited_industries=contract_cfg.get(
            "prohibited_industries",
            uw.get("prohibited_industries", ["Fireworks", "CryptoMining"]),
        ),
    )


def build_llm(config: Dict[str, Any], use_mock: bool = False) -> Any:
    if use_mock:
        return MockLLM()
    defaults = config.get("llm_defaults", {})
    model = defaults.get("model", "gemma3:4b")
    base_url = defaults.get("base_url", "http://localhost:11434")
    return OllamaClient(model=model, base_url=base_url)

