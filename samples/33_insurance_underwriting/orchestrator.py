"""
Email ingestion orchestrator: DFID, ROA, DIM, mock bind, canonical audit.

One markdown email = one DecisionFlow. Expects ``AgentRegistry.handshake`` in ``run.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from dir_core import AgentRegistry, ContextStore, new_dfid
from dir_core.storage import AuditStore, StorageBundle
from dir_core.utils.logging_utils import log_context
from email_fixture_ingest import (
    client_application_from_fixture,
    list_markdown_fixtures,
    load_markdown_email_fixture,
)
from kernel import DecisionIntegrityModule, DecisionLedger
from policy_binding import PolicyBindingClient

from agent import ROAUnderwriterAgent
from telemetry import record_underwriting_step

logger = logging.getLogger(__name__)


def _parse_reason_codes(dim_out: str) -> list[str]:
    if dim_out == "Policy Bound":
        return []
    return [code.strip() for code in dim_out.split(";") if code.strip()]


def _terminal_from_dim(dim_out: str) -> tuple[str, str, str, list[str]]:
    """Map DIM result to (outcome, reason_code, lifecycle_state, reason_codes)."""
    if dim_out == "Policy Bound":
        return "BOUND", "POLICY_BOUND", "CLOSED", []
    reason_codes = _parse_reason_codes(dim_out)
    reason_code = ";".join(reason_codes)
    if reason_codes == ["AUTHORITY_CEILING"]:
        return "ESCALATED", reason_code, "ESCALATED", reason_codes
    return "REJECTED", reason_code, "ABORTED", reason_codes


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
) -> str:
    dfid = new_dfid()
    with log_context(dfid=dfid):
        ep = config.get("email_processing", {})
        fx = {k.upper(): float(v) for k, v in ep.get("currency_fx_to_usd", {}).items()}
        agent_id = str((contract_dict.get("subject") or {}).get("agent_id", ""))

        logger.info("FLOW_CREATED file=%s", path.name)
        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "FLOW_CREATED",
            step_id="0",
            state="CREATED",
            details={"file": path.name},
            agent_id=agent_id,
        )

        fixture = load_markdown_email_fixture(path)
        context = client_application_from_fixture(fixture)
        context_store.update_session(dfid, context.model_dump(), agent_id=agent_id)

        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "MAIL_INGESTED",
            state="CREATED",
            details={
                "file": path.name,
                "subject": context.mail_subject,
                "mail_body_sha256": context.mail_body_sha256,
            },
            agent_id=agent_id,
        )
        logger.info(
            "MAIL_INGESTED file=%s mail_body_sha256=%s",
            path.name,
            context.mail_body_sha256,
        )

        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "CONTEXT_COMPILED",
            state="ACTIVE",
            details={"industry": context.industry},
            agent_id=agent_id,
        )
        logger.info("CONTEXT_COMPILED")

        try:
            proposal = agent.explain_and_formulate_policy(
                fixture.body_text,
                context,
                fx,
            )
        except (ValueError, TypeError) as exc:
            record_underwriting_step(
                audit,
                dfid,
                simulation_id,
                "POLICY_PROPOSAL_FAILED",
                state="ABORTED",
                details={"error": str(exc)},
                agent_id=agent_id,
            )
            logger.warning("POLICY_PROPOSAL_FAILED: %s", exc)
            record_underwriting_step(
                audit,
                dfid,
                simulation_id,
                "FLOW_TERMINAL",
                state="ABORTED",
                details={
                    "outcome": "REJECTED",
                    "reason_code": "PROPOSAL_FAILED",
                    "lifecycle_state": "ABORTED",
                },
                agent_id=agent_id,
            )
            return dfid

        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "POLICY_PROPOSED",
            state="ACTIVE",
            details={
                "total_insured_value": proposal.total_insured_value,
                "territory": proposal.territory,
                "justification": proposal.justification,
            },
            agent_id=agent_id,
        )
        logger.info(
            "POLICY_PROPOSED total_insured_value=%s",
            proposal.total_insured_value,
        )

        cycle = agent.run_decision_cycle(
            context,
            dfid=dfid,
            proposal=proposal,
        )
        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "PCI_EMITTED",
            state="VALIDATING",
            details={
                "total_insured_value": cycle.proposal.total_insured_value,
                "territory": cycle.proposal.territory,
                "justification": cycle.proposal.justification,
                "evidence_hash": cycle.pci.evidence_hash,
            },
            agent_id=agent_id,
        )
        logger.info(
            "PCI_EMITTED total_insured_value=%.0f",
            cycle.proposal.total_insured_value,
        )

        dim_out = dim.verify_and_commit(cycle.pci, agent_id)
        reason_codes = _parse_reason_codes(dim_out)
        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "DIM_RESULT",
            state="VALIDATING",
            details={"result": dim_out, "reason_codes": reason_codes},
            agent_id=agent_id,
        )
        logger.info("DIM_RESULT %s", dim_out)

        outcome, reason_code, lifecycle_state, reason_codes = _terminal_from_dim(dim_out)
        if dim_out != "Policy Bound":
            ev = (
                "GATE_AUTHORITY_ESCALATED"
                if reason_codes == ["AUTHORITY_CEILING"]
                else "GATE_REJECTED"
            )
            record_underwriting_step(
                audit,
                dfid,
                simulation_id,
                ev,
                state=lifecycle_state,
                details={
                    "code": reason_code,
                    "reason_codes": reason_codes,
                    "message": dim_out,
                },
                agent_id=agent_id,
            )
            logger.info("%s code=%s", ev, reason_code)
            record_underwriting_step(
                audit,
                dfid,
                simulation_id,
                "FLOW_TERMINAL",
                state=lifecycle_state,
                details={
                    "outcome": outcome,
                    "reason_code": reason_code,
                    "reason_codes": reason_codes,
                    "lifecycle_state": lifecycle_state,
                },
                agent_id=agent_id,
            )
            return dfid

        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "LEDGER_COMMITTED",
            state="ACCEPTED",
            details={},
            agent_id=agent_id,
        )
        logger.info("LEDGER_COMMITTED")

        br = binder.bind_policy(
            dfid,
            simulation_id=simulation_id,
            total_insured_value=cycle.proposal.total_insured_value,
        )
        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "BIND_SUCCEEDED",
            state="CLOSED",
            details={"policy_ref": br.policy_ref, "cached": br.cached},
            agent_id=agent_id,
        )
        logger.info("FLOW_TERMINAL outcome=BOUND policy_ref=%s", br.policy_ref)
        record_underwriting_step(
            audit,
            dfid,
            simulation_id,
            "FLOW_TERMINAL",
            state="CLOSED",
            details={
                "outcome": "BOUND",
                "reason_code": "POLICY_BOUND",
                "lifecycle_state": "CLOSED",
                "policy_ref": br.policy_ref,
            },
            agent_id=agent_id,
        )
        return dfid


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
) -> tuple[List[str], DecisionLedger]:
    contract_dict = dict(config["agents"][0]["contract"])
    agent_id = str((contract_dict.get("subject") or {}).get("agent_id", ""))

    if context_store is None:
        context_store = ContextStore(storage=bundle.context)
    ledger = DecisionLedger(storage=bundle.decision_ledger)
    dim = DecisionIntegrityModule(registry, context_store, ledger)
    agent = ROAUnderwriterAgent(registry, agent_id, llm)
    binder = PolicyBindingClient(audit)

    ep = config.get("email_processing", {})
    emails_dir = sample_dir / ep.get("emails_dir", "emails")
    paths = list_markdown_fixtures(emails_dir)

    dfids: List[str] = []
    for path in paths:
        dfids.append(
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
    return dfids, ledger
