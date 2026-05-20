"""``StorageBundle.decision_audit`` helpers — canonical ``decision_audit_events`` rows.

Aligned with ``src/dir_core/storage/schema.sql`` and
``.cursor/rules/07-telemetry-guidelines.md``:

* ``root_dfid`` = ``simulation_id`` for every row (run lineage); per-scenario ``dfid``
  stays the execution identifier.
* ``detail_json`` includes ``correlation_id`` (and optional ``causation_id``).
* ``step_id`` / ``state`` / ``severity`` use top-level columns, not prose-only logs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dir_core.storage import StorageBundle


def _detail_base(
    simulation_id: str,
    extra: Optional[Dict[str, Any]] = None,
    *,
    causation_id: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "correlation_id": simulation_id,
    }
    if causation_id:
        out["causation_id"] = causation_id
    if extra:
        out.update(extra)
    return out


def record_simulation_start(
    bundle: StorageBundle,
    simulation_id: str,
    *,
    llm_backend: str = "",
    sample: str = "34_langchain_roa_wrapper",
) -> None:
    extra: Dict[str, Any] = {"sample": sample}
    if llm_backend:
        extra["llm_backend"] = llm_backend
    bundle.decision_audit.record(
        simulation_id,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=_detail_base(simulation_id, extra),
        root_dfid=simulation_id,
        severity="INFO",
    )


def record_simulation_end(
    bundle: StorageBundle,
    simulation_id: str,
    *,
    status: str,
    error_message: str = "",
) -> None:
    extra: Dict[str, Any] = {"status": status}
    if error_message:
        extra["error_message"] = error_message
    sev = "ERROR" if status.lower() == "error" else "INFO"
    bundle.decision_audit.record(
        simulation_id,
        "SIMULATION_END",
        step_id="SIMULATION",
        state=status.upper(),
        details=_detail_base(simulation_id, extra),
        root_dfid=simulation_id,
        severity=sev,
    )


def record_agent_decision(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    verdict: str,
    reason: str,
    confidence: float,
    justification: str,
    scenario_label: str = "",
    executed: bool = False,
    resource_id: str = "",
    explain_narrative: str = "",
    explain_signals: Optional[List[Any]] = None,
    explain_risks: Optional[List[Any]] = None,
    explain_opportunities: Optional[List[Any]] = None,
    self_check_passed: bool = True,
    self_check_reason: str = "",
    contract_role: str = "",
    contract_allowed_policy_types: Optional[List[str]] = None,
) -> None:
    details: Dict[str, Any] = {
        "agent_id": agent_id,
        "policy_kind": policy_kind,
        "verdict": verdict,
        "reason": reason,
        "confidence": confidence,
        "justification": justification,
        "scenario_label": scenario_label,
        "executed": executed,
        "resource_id": resource_id,
        "self_check_passed": self_check_passed,
        "self_check_reason": self_check_reason,
        "contract_role": contract_role,
    }
    if contract_allowed_policy_types is not None:
        details["contract_allowed_policy_types"] = contract_allowed_policy_types
    if explain_narrative:
        details["explain_narrative"] = explain_narrative
    if explain_signals:
        details["explain_signals"] = explain_signals
    if explain_risks:
        details["explain_risks"] = explain_risks
    if explain_opportunities:
        details["explain_opportunities"] = explain_opportunities
    v_upper = str(verdict).upper()
    sev = "INFO"
    if v_upper in ("REJECT", "ESCALATE"):
        sev = "WARNING"
    bundle.decision_audit.record(
        dfid,
        "AGENT_DECISION",
        step_id="ROA_DIM",
        state=v_upper,
        details=_detail_base(simulation_id, details),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )


def record_self_check_failed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    scenario_label: str = "",
    explain_narrative: str = "",
    explain_signals: Optional[List[Any]] = None,
    explain_risks: Optional[List[Any]] = None,
    explain_opportunities: Optional[List[Any]] = None,
) -> None:
    det: Dict[str, Any] = {
        "agent_id": agent_id,
        "reason": reason,
        "scenario_label": scenario_label,
    }
    if explain_narrative:
        det["explain_narrative"] = explain_narrative
    if explain_signals:
        det["explain_signals"] = explain_signals
    if explain_risks:
        det["explain_risks"] = explain_risks
    if explain_opportunities:
        det["explain_opportunities"] = explain_opportunities
    bundle.decision_audit.record(
        dfid,
        "FINOPS_SELF_CHECK_FAILED",
        step_id="SELF_CHECK",
        state="FAILED",
        details=_detail_base(simulation_id, det),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING",
    )


def record_finops_execution(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    resource_id: str,
    idempotency_key_value: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "FINOPS_EXECUTION",
        step_id="FINOPS_EXECUTION",
        state="DRY_RUN",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "policy_kind": policy_kind,
                "resource_id": resource_id,
                "idempotency_key": idempotency_key_value,
                "mode": "dry_run",
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )
