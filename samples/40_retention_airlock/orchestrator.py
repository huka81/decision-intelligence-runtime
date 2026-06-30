"""Scenario orchestration: ROA cycle, airlock gates, escalation, drift sweep."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dir_core import DecisionRuntime, IntentRetryGovernor, PolicyProposal, idempotency_key, new_dfid
from dir_core.data_types import DimReasonCode, ValidationVerdict
from dir_core.escalation import ImpactCategory
from dir_core.models import ResponsibilityContract
from dir_core.storage import StorageBundle
from dir_core.utils.logging_utils import log_with_dfid

from agent import run_retention_roa_cycle
from context_tax import build_prior_failure_trace, estimate_context_tokens
from dim import build_dim_context, dim_validators, gate_trace_from_reason
from reconstruction import evaluate_bidirectional_reconstruction
from schemas import (
    ContextTaxAttempt,
    DriftSweepConfig,
    DriftSweepResult,
    RetentionAirlockConfig,
    ScenarioConfig,
    ScenarioResult,
    max_discount_for_tier,
)
from telemetry import (
    record_agent_decision_summary,
    record_airlock_gate,
    record_context_compiled,
    record_context_tax,
    record_dim_validation,
    record_escalation_requested,
    record_policy_proposal,
    record_retention_executed,
)
from temporal_monitor import TemporalGovernanceMonitor

logger = logging.getLogger(__name__)


@dataclass
class PhaseAResult:
    scenarios: List[ScenarioResult] = field(default_factory=list)


def _verdict_str(verdict: Any) -> str:
    return verdict.value if hasattr(verdict, "value") else str(verdict)


def _discount_from_proposal(proposal: PolicyProposal) -> float:
    try:
        return float(proposal.params.get("discount_pct", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _record_gate_trace(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    agent_id: str,
    trace: Dict[str, str],
    reason: str,
) -> None:
    for gate, state in trace.items():
        record_airlock_gate(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            gate=gate,
            state=state,
            reason=reason if state != "PASS" else "",
        )


def _execute_proposal(
    bundle: StorageBundle,
    proposal: PolicyProposal,
    *,
    simulation_id: str,
    agent_id: str,
) -> bool:
    if proposal.policy_kind != "APPLY_DISCOUNT":
        return False
    discount = _discount_from_proposal(proposal)
    record_retention_executed(
        bundle,
        proposal.dfid,
        simulation_id,
        agent_id=agent_id,
        policy_kind=proposal.policy_kind,
        discount_pct=discount,
        proposal_dump=proposal.model_dump(mode="json"),
    )
    # Idempotency key demonstrates DIR execution contract (no external PSP in this sample).
    _ = idempotency_key(proposal.dfid, "RETENTION_EXECUTED", proposal.params)
    return True


def process_scenario(
    runtime: DecisionRuntime,
    bundle: StorageBundle,
    contract: ResponsibilityContract,
    llm: Any,
    scenario: ScenarioConfig,
    airlock: RetentionAirlockConfig,
    *,
    simulation_id: str,
    agent_id: str,
) -> ScenarioResult:
    dfid = new_dfid()
    max_disc = max_discount_for_tier(airlock, scenario.customer_tier)
    dim_ctx = build_dim_context(
        customer_id=scenario.customer_id,
        customer_tier=scenario.customer_tier,
        email_body=scenario.email_body,
        max_discount_pct=max_disc,
        cancel_intent_patterns=airlock.cancel_intent_patterns,
        retention_actions=airlock.retention_actions,
        dfid=dfid,
        agent_id=agent_id,
        enable_bidirectional_reconstruction=scenario.enable_bidirectional_reconstruction,
        bidirectional_min_overlap=airlock.bidirectional.min_keyword_overlap,
        bidirectional_salient_terms=airlock.bidirectional.salient_terms,
    )

    runtime.context_store.update_session(
        dfid,
        {
            "scenario": scenario.label,
            "customer_id": scenario.customer_id,
            "email_body": scenario.email_body,
        },
    )
    record_context_compiled(
        bundle,
        dfid,
        simulation_id,
        agent_id=agent_id,
        scenario_label=scenario.label,
        customer_id=scenario.customer_id,
    )

    retry_governor = IntentRetryGovernor(max_retries=airlock.intent_retry_max)
    retry_count = 0
    final_verdict = "REJECT"
    dim_reason = ""
    executed = False
    escalated = False
    proposal: Optional[PolicyProposal] = None
    narrative = ""
    justification = ""
    policy_kind = ""
    discount_pct = 0.0
    airlock_trace: Dict[str, str] = {}
    reconstructed_narrative = ""
    keyword_overlap_score = 0.0
    failure_history: List[str] = []
    context_tax_attempts: List[ContextTaxAttempt] = []

    while True:
        prior_trace = build_prior_failure_trace(failure_history)
        estimated_tokens = estimate_context_tokens(retry_count)
        record_context_tax(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            retry_attempt=retry_count,
            estimated_tokens=estimated_tokens,
            prior_failure_trace=prior_trace,
        )
        context_tax_attempts.append(
            ContextTaxAttempt(
                attempt=retry_count + 1,
                estimated_tokens=estimated_tokens,
                prior_failure_trace=prior_trace,
            )
        )

        proposal, narrative, justification, roa_fail = run_retention_roa_cycle(
            llm,
            contract,
            dfid=dfid,
            agent_id=agent_id,
            scenario_label=scenario.label,
            customer_id=scenario.customer_id,
            customer_tier=scenario.customer_tier,
            email_body=scenario.email_body,
            mock_policy_kind=scenario.mock_policy_kind,
            mock_discount_pct=scenario.mock_discount_pct,
            retry_attempt=retry_count,
            prior_failure_trace=prior_trace,
        )
        if proposal is None:
            final_verdict = "REJECT"
            dim_reason = roa_fail
            airlock_trace = {
                "syntactic": "REJECT",
                "fact_validation": "SKIP",
                "evidence_validation": "SKIP",
                "bidirectional_reconstruction": "SKIP",
            }
            break

        policy_kind = proposal.policy_kind
        discount_pct = _discount_from_proposal(proposal)
        record_policy_proposal(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            policy_kind=policy_kind,
            params=dict(proposal.params),
            retry_attempt=retry_count,
        )

        verdict, reason = runtime.evaluate_proposal(
            proposal,
            {"email_body": scenario.email_body},
            dim_context=dim_ctx,
            allowed_agents=[agent_id],
            contract=contract.model_dump(),
            custom_validators=dim_validators(),
            retry_governor=retry_governor,
            record_audit=False,
        )
        dim_reason = str(reason)
        airlock_trace = gate_trace_from_reason(dim_reason)
        _record_gate_trace(
            bundle, dfid, simulation_id, agent_id, airlock_trace, dim_reason
        )
        record_dim_validation(
            bundle,
            dfid,
            simulation_id,
            agent_id=agent_id,
            verdict=_verdict_str(verdict),
            reason=dim_reason,
            retry_count=retry_count,
        )

        if verdict == ValidationVerdict.ACCEPT:
            final_verdict = "ACCEPT"
            executed = _execute_proposal(
                bundle, proposal, simulation_id=simulation_id, agent_id=agent_id
            )
            break

        if "EVIDENTIAL_CONFLICT" in dim_reason or "COMPRESSION_DRIFT" in dim_reason:
            if "COMPRESSION_DRIFT" in dim_reason and proposal is not None:
                _passed, reconstructed_narrative, keyword_overlap_score = (
                    evaluate_bidirectional_reconstruction(
                        scenario.email_body,
                        proposal.model_dump(mode="json"),
                        min_overlap=airlock.bidirectional.min_keyword_overlap,
                        salient_terms=airlock.bidirectional.salient_terms,
                    )
                )
            esc = runtime.escalation.request_escalation(
                dfid,
                agent_id,
                dim_reason,
                dim_ctx,
                proposal,
                ImpactCategory.HIGH_IMPACT,
            )
            if esc.value == "GRANTED":
                record_escalation_requested(
                    bundle,
                    dfid,
                    simulation_id,
                    agent_id=agent_id,
                    reason=dim_reason,
                )
            final_verdict = "ESCALATE"
            escalated = True
            break

        if retry_governor.should_abort(dfid):
            final_verdict = "REJECT"
            dim_reason = str(DimReasonCode.REASONING_EXHAUSTION)
            airlock_trace = gate_trace_from_reason(dim_reason)
            log_with_dfid(
                logger,
                dfid,
                logging.WARNING,
                "Intent Retry Governor: %s",
                dim_reason,
            )
            break

        if not scenario.retry_until_exhaustion:
            final_verdict = "REJECT"
            break

        failure_history.append(dim_reason)
        retry_count += 1

    record_agent_decision_summary(
        bundle,
        dfid,
        simulation_id,
        agent_id=agent_id,
        scenario_label=scenario.label,
        policy_kind=policy_kind,
        verdict=final_verdict,
        reason=dim_reason,
        confidence=(proposal.confidence if proposal else 0.0),
        justification=justification,
        explain_narrative=narrative,
        airlock_trace=airlock_trace,
        reconstructed_narrative=reconstructed_narrative,
        keyword_overlap=keyword_overlap_score,
    )

    return ScenarioResult(
        label=scenario.label,
        dfid=dfid,
        expected=scenario.expected,
        final_verdict=final_verdict,
        dim_reason=dim_reason,
        executed=executed,
        retry_count=retry_count,
        airlock_trace=airlock_trace,
        explain_narrative=narrative,
        justification=justification,
        policy_kind=policy_kind,
        discount_pct=discount_pct,
        escalated=escalated,
        reconstructed_narrative=reconstructed_narrative,
        keyword_overlap=keyword_overlap_score,
        context_tax_attempts=context_tax_attempts,
        email_body=scenario.email_body,
    )


def run_defense_scenarios(
    runtime: DecisionRuntime,
    bundle: StorageBundle,
    contract: ResponsibilityContract,
    llm: Any,
    scenarios: List[ScenarioConfig],
    airlock: RetentionAirlockConfig,
    *,
    simulation_id: str,
    agent_id: str,
) -> PhaseAResult:
    out = PhaseAResult()
    for scenario in scenarios:
        result = process_scenario(
            runtime,
            bundle,
            contract,
            llm,
            scenario,
            airlock,
            simulation_id=simulation_id,
            agent_id=agent_id,
        )
        out.scenarios.append(result)
        log_with_dfid(
            logger,
            result.dfid,
            logging.INFO,
            "[SCENARIO] %s expected=%s actual=%s executed=%s",
            result.label,
            result.expected,
            result.final_verdict,
            result.executed,
        )
        if result.context_tax_attempts and "efficiency_trap" in result.label:
            tax_parts = " | ".join(
                f"retry {a.attempt}: ~{a.estimated_tokens} tokens"
                for a in result.context_tax_attempts
            )
            log_with_dfid(
                logger,
                result.dfid,
                logging.INFO,
                "[CONTEXT_TAX] %s",
                tax_parts,
            )
    return out


def run_drift_sweep(
    runtime: DecisionRuntime,
    bundle: StorageBundle,
    contract: ResponsibilityContract,
    llm: Any,
    sweep: DriftSweepConfig,
    airlock: RetentionAirlockConfig,
    monitor: TemporalGovernanceMonitor,
    *,
    simulation_id: str,
    agent_id: str,
) -> DriftSweepResult:
    result = DriftSweepResult()
    runtime.registry.set_agent_status(agent_id, "ACTIVE", "drift_sweep_start")

    for i in range(1, sweep.iterations + 1):
        st = runtime.registry.get_agent_status(agent_id)
        if st and st[0] == "SUSPENDED":
            result.stopped_reason = "agent_already_suspended"
            break

        scenario = ScenarioConfig(
            label=f"5_temporal_drift_sweep_{i:02d}",
            customer_id=sweep.customer_id,
            customer_tier=sweep.customer_tier,
            email_body=sweep.email_template,
            mock_policy_kind="APPLY_DISCOUNT",
            mock_discount_pct=sweep.mock_discount_pct,
            expected="ACCEPT",
            enable_bidirectional_reconstruction=False,
            notes="Temporal drift batch iteration",
        )
        step = process_scenario(
            runtime,
            bundle,
            contract,
            llm,
            scenario,
            airlock,
            simulation_id=simulation_id,
            agent_id=agent_id,
        )
        result.steps.append(step)

        if step.executed:
            suspended, _avg = monitor.evaluate_after_execution(step.dfid)
            if suspended:
                result.suspended = True
                result.suspension_iteration = i
                result.stopped_reason = "circuit_breaker_triggered"
                break

    if not result.stopped_reason:
        result.stopped_reason = "completed"
    return result
