"""Credit-limit decision orchestrator: evidence → alignment → PCI → DIM → execute."""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Optional

from dir_core import DecisionRuntime, PolicyProposal, new_dfid
from dir_core.data_types import ValidationVerdict
from dir_core.ledger import DecisionLedger
from dir_core.storage import StorageBundle
from dir_core.utils.logging_utils import log_with_dfid

from alignment import check_semantic_alignment
from dim import dim_validators
from evidence import run_evidence_gates
from limit_client import CreditLimitClient
from pci_builder import build_pci, contract_hash_for_agent, verify_pci
from schemas import (
    CaseResult,
    CreditLimitGateConfig,
    ScenarioConfig,
    SemanticAlignmentConfig,
    is_high_risk_approval,
)
from telemetry import (
    record_credit_decision,
    record_credit_limit_raised,
    record_evidence_abort,
    record_pci_verification,
    record_semantic_alignment_abort,
    record_semantic_alignment_flag,
)

logger = logging.getLogger(__name__)

AGENT_ID = "credit_limit_agent"


def process_credit_request(
    scenario: ScenarioConfig,
    *,
    bundle: StorageBundle,
    runtime: DecisionRuntime,
    contract: Dict[str, Any],
    contract_hash: str,
    simulation_id: str,
    gate_config: CreditLimitGateConfig,
    alignment_config: SemanticAlignmentConfig,
    limit_client: CreditLimitClient,
    ledger: DecisionLedger,
) -> CaseResult:
    dfid = new_dfid()
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "=== Scenario: %s (%s) ===",
        scenario.label,
        scenario.defense_layer,
    )

    context = {"chat_transcript": scenario.chat_transcript}
    runtime.context_store.update_session(dfid, context)
    dim_ctx = runtime.context_store.compile_working_context(AGENT_ID, dfid)
    dim_ctx["max_limit_pln"] = gate_config.max_limit_pln

    claim = dict(scenario.claim)
    justification = scenario.justification

    if scenario.skip_evidence_governance:
        return _baseline_no_evidence(
            dfid=dfid,
            scenario=scenario,
            bundle=bundle,
            runtime=runtime,
            contract=contract,
            dim_ctx=dim_ctx,
            claim=claim,
            justification=justification,
            simulation_id=simulation_id,
            limit_client=limit_client,
            gate_config=gate_config,
        )

    evidence = run_evidence_gates(
        claim,
        scenario.chat_transcript,
        enable_heuristic=scenario.enable_heuristic,
        enable_reconstruction=scenario.enable_reconstruction,
    )
    if not evidence.passed:
        log_with_dfid(
            logger,
            dfid,
            logging.ERROR,
            "[User Space] ABORT — %s",
            evidence.reason,
        )
        record_evidence_abort(
            bundle,
            dfid,
            simulation_id,
            agent_id=AGENT_ID,
            reason=evidence.reason,
            scenario_label=scenario.label,
        )
        return CaseResult(
            dfid=dfid,
            scenario_label=scenario.label,
            final_status="EVIDENCE_ABORT",
            reason=evidence.reason,
            executed=False,
            evidence_passed=False,
        )

    strict = (
        scenario.strict_alignment
        if scenario.strict_alignment is not None
        else alignment_config.strict_blocking
    )
    alignment = check_semantic_alignment(
        justification,
        alignment_config,
        strict_blocking=strict,
    )
    if alignment.aborted:
        log_with_dfid(
            logger,
            dfid,
            logging.ERROR,
            "[User Space] ABORT — %s",
            alignment.reason,
        )
        record_semantic_alignment_abort(
            bundle,
            dfid,
            simulation_id,
            agent_id=AGENT_ID,
            reason=alignment.reason,
            scenario_label=scenario.label,
        )
        return CaseResult(
            dfid=dfid,
            scenario_label=scenario.label,
            final_status="ALIGNMENT_ABORT",
            reason=alignment.reason,
            executed=False,
            evidence_passed=True,
            alignment_flag=alignment.flag,
        )

    if alignment.flag == "NEEDS_REVIEW":
        record_semantic_alignment_flag(
            bundle,
            dfid,
            simulation_id,
            agent_id=AGENT_ID,
            flag=alignment.flag,
            reason=alignment.reason,
            scenario_label=scenario.label,
        )
        log_with_dfid(
            logger,
            dfid,
            logging.WARNING,
            "[User Space] Semantic alignment flag: %s",
            alignment.flag,
        )

    pci = build_pci(
        dfid,
        claim,
        context,
        contract_hash,
        justification,
    )

    if scenario.tamper_pci:
        pci = copy.deepcopy(pci)
        tampered = dict(pci.intent_payload)
        tampered["params"] = {
            **claim,
            "declared_income_pln": 30000,
            "requested_limit_pln": 9500,
        }
        pci.intent_payload = tampered
        log_with_dfid(
            logger,
            dfid,
            logging.WARNING,
            "[Attack] Tampered PCI params after signing",
        )

    proof_ok, proof_reason = verify_pci(pci, context, contract_hash)
    record_pci_verification(
        bundle,
        dfid,
        simulation_id,
        agent_id=AGENT_ID,
        proof_ok=proof_ok,
        reason=proof_reason,
        scenario_label=scenario.label,
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "[Kernel Space] ProofChecker: %s (%s)",
        proof_ok,
        proof_reason,
    )

    if not proof_ok:
        return CaseResult(
            dfid=dfid,
            scenario_label=scenario.label,
            final_status="PCI_REJECT",
            reason=proof_reason,
            executed=False,
            proof_ok=False,
            evidence_passed=True,
            alignment_flag=alignment.flag,
        )

    ledger.append(pci)

    payload = pci.intent_payload
    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=AGENT_ID,
        policy_kind=str(payload.get("policy_kind", "RAISE_LIMIT")),
        params=dict(payload.get("params", {})),
        context_ref=pci.context_ref,
        confidence=float(payload.get("confidence", 1.0)),
        justification=str(payload.get("justification", "")),
    )

    verdict, dim_reason = runtime.evaluate_proposal(
        proposal,
        {},
        dim_context=dim_ctx,
        allowed_agents=[AGENT_ID],
        contract=contract,
        use_registry_contract=False,
        custom_validators=dim_validators(),
    )
    record_credit_decision(
        bundle,
        dfid,
        simulation_id,
        agent_id=AGENT_ID,
        verdict=str(verdict),
        reason=str(dim_reason),
        scenario_label=scenario.label,
    )

    executed = False
    if verdict == ValidationVerdict.ACCEPT:
        params = proposal.params
        high_risk = is_high_risk_approval(
            float(params.get("declared_income_pln", 0)),
            float(params.get("requested_limit_pln", 0)),
            gate_config.min_income_to_limit_ratio,
        )
        result = limit_client.raise_limit(
            dfid,
            simulation_id=simulation_id,
            customer_id=str(params.get("customer_id", "")),
            new_limit_pln=float(params.get("requested_limit_pln", 0)),
            declared_income_pln=float(params.get("declared_income_pln", 0)),
        )
        if result.ok:
            executed = True
            record_credit_limit_raised(
                bundle,
                dfid,
                simulation_id,
                agent_id=AGENT_ID,
                customer_id=str(params.get("customer_id", "")),
                new_limit_pln=result.new_limit_pln,
                high_risk=high_risk,
                declared_income_pln=float(params.get("declared_income_pln", 0)),
                idempotency_key_prefix=result.idempotency_key[:16],
                scenario_label=scenario.label,
            )
            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "[Execution] Limit raised to %.0f PLN (high_risk=%s)",
                result.new_limit_pln,
                high_risk,
            )

    return CaseResult(
        dfid=dfid,
        scenario_label=scenario.label,
        final_status=str(verdict),
        reason=str(dim_reason),
        executed=executed,
        proof_ok=True,
        evidence_passed=True,
        alignment_flag=alignment.flag,
        dim_verdict=str(verdict),
    )


def _baseline_no_evidence(
    *,
    dfid: str,
    scenario: ScenarioConfig,
    bundle: StorageBundle,
    runtime: DecisionRuntime,
    contract: Dict[str, Any],
    dim_ctx: Dict[str, Any],
    claim: Dict[str, Any],
    justification: str,
    simulation_id: str,
    limit_client: CreditLimitClient,
    gate_config: CreditLimitGateConfig,
) -> CaseResult:
    log_with_dfid(
        logger,
        dfid,
        logging.WARNING,
        "[Baseline] No Evidence Governance — submitting Compliant Lie directly to DIM",
    )
    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=AGENT_ID,
        policy_kind="RAISE_LIMIT",
        params=claim,
        confidence=0.95,
        justification=justification,
    )
    verdict, dim_reason = runtime.evaluate_proposal(
        proposal,
        {},
        dim_context=dim_ctx,
        allowed_agents=[AGENT_ID],
        contract=contract,
        use_registry_contract=False,
        custom_validators=dim_validators(),
    )
    record_credit_decision(
        bundle,
        dfid,
        simulation_id,
        agent_id=AGENT_ID,
        verdict=str(verdict),
        reason=str(dim_reason),
        scenario_label=scenario.label,
    )

    executed = False
    if verdict == ValidationVerdict.ACCEPT:
        high_risk = is_high_risk_approval(
            float(claim.get("declared_income_pln", 0)),
            float(claim.get("requested_limit_pln", 0)),
            gate_config.min_income_to_limit_ratio,
        )
        result = limit_client.raise_limit(
            dfid,
            simulation_id=simulation_id,
            customer_id=str(claim.get("customer_id", "")),
            new_limit_pln=float(claim.get("requested_limit_pln", 0)),
            declared_income_pln=float(claim.get("declared_income_pln", 0)),
        )
        if result.ok:
            executed = True
            record_credit_limit_raised(
                bundle,
                dfid,
                simulation_id,
                agent_id=AGENT_ID,
                customer_id=str(claim.get("customer_id", "")),
                new_limit_pln=result.new_limit_pln,
                high_risk=high_risk,
                declared_income_pln=float(claim.get("declared_income_pln", 0)),
                idempotency_key_prefix=result.idempotency_key[:16],
                scenario_label=scenario.label,
            )
            log_with_dfid(
                logger,
                dfid,
                logging.WARNING,
                "[Execution] Catastrophic: limit raised on hallucinated income",
            )

    return CaseResult(
        dfid=dfid,
        scenario_label=scenario.label,
        final_status=str(verdict),
        reason=str(dim_reason),
        executed=executed,
        evidence_passed=None,
        dim_verdict=str(verdict),
    )


def process_drift_iteration(
    *,
    iteration: int,
    bundle: StorageBundle,
    runtime: DecisionRuntime,
    contract: Dict[str, Any],
    contract_hash: str,
    simulation_id: str,
    gate_config: CreditLimitGateConfig,
    alignment_config: SemanticAlignmentConfig,
    limit_client: CreditLimitClient,
    ledger: DecisionLedger,
    drift_config: Dict[str, Any],
    chat_phrase: str,
) -> CaseResult:
    """One drift-batch iteration with full evidence pipeline."""
    income = (
        drift_config.get("phase1_income_pln", 4000)
        if iteration <= int(drift_config.get("phase1_iterations", 5))
        else drift_config.get("phase2_income_pln", 2200)
    )
    limit = (
        drift_config.get("phase1_limit_pln", 8000)
        if iteration <= int(drift_config.get("phase1_iterations", 5))
        else drift_config.get("phase2_limit_pln", 9000)
    )
    chat = (
        f"Customer: my monthly income is {int(income)} PLN. {chat_phrase} "
        f"Please raise my limit to {int(limit)} PLN."
    )
    claim = {
        "customer_id": f"drift_cust_{iteration:02d}",
        "declared_income_pln": float(income),
        "requested_limit_pln": float(limit),
        "current_limit_pln": 5000.0,
    }
    justification = (
        f"Priority article phrase acknowledged. Declared income {income} PLN "
        f"supports limit {limit} PLN per payment history."
    )
    scenario = ScenarioConfig(
        label=f"drift_{iteration:02d}",
        defense_layer="async_audit",
        chat_transcript=chat,
        claim=claim,
        justification=justification,
        expected="ACCEPT",
    )
    return process_credit_request(
        scenario,
        bundle=bundle,
        runtime=runtime,
        contract=contract,
        contract_hash=contract_hash,
        simulation_id=simulation_id,
        gate_config=gate_config,
        alignment_config=alignment_config,
        limit_client=limit_client,
        ledger=ledger,
    )

