"""``AuditStore`` helpers — canonical decision audit rows for ROA demo runs.

Aligned with ``src/dir_core/storage/schema.sql`` and telemetry guidelines:

* ``root_dfid`` = ``simulation_id`` for the whole script run.
* Per-cycle rows use the scenario ``dfid`` with the same ``root_dfid``.
* ``detail_json`` includes ``correlation_id`` (= ``simulation_id``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from dir_core import EscalationRequest, PolicyProposal
from dir_core.storage.base import AuditStore

SIMULATION_ID = "sample_01_roa_agent"


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
    audit: AuditStore,
    simulation_id: str = SIMULATION_ID,
    *,
    sample: str = "01_roa_agent",
) -> None:
    audit.record(
        simulation_id,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=_detail_base(
            simulation_id,
            {
                "sample": sample,
                "mode": "roa_educational_demo",
            },
        ),
        root_dfid=simulation_id,
        severity="INFO",
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str = SIMULATION_ID,
    *,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    extra: Dict[str, Any] = {"status": status}
    if error_message is not None:
        extra["error_message"] = error_message
    sev = "ERROR" if status.lower() == "error" else "INFO"
    audit.record(
        simulation_id,
        "SIMULATION_END",
        step_id="SIMULATION",
        state=status.upper(),
        details=_detail_base(simulation_id, extra),
        root_dfid=simulation_id,
        severity=sev,
    )


def record_roa_cycle_result(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    result: Union[PolicyProposal, EscalationRequest],
    *,
    scenario_label: str,
) -> None:
    """Emit one audit row per ``run_decision_cycle`` outcome."""
    if isinstance(result, PolicyProposal):
        pk = str(result.policy_kind)
        st = pk.upper().replace(" ", "_")[:120]
        audit.record(
            dfid,
            "AGENT_DECISION",
            step_id="ROA_CYCLE",
            state=st,
            details=_detail_base(
                simulation_id,
                {
                    "scenario": scenario_label,
                    "agent_id": result.agent_id,
                    "policy_kind": result.policy_kind,
                    "confidence": result.confidence,
                    "justification": (result.justification or "")[:500],
                },
            ),
            root_dfid=simulation_id,
            agent_id=result.agent_id,
            severity="INFO",
        )
        return

    sev_esc = str(result.severity)
    audit.record(
        dfid,
        "ESCALATION_REQUESTED",
        step_id="ROA_ESCALATION",
        state="PENDING",
        details=_detail_base(
            simulation_id,
            {
                "scenario": scenario_label,
                "from_agent_id": result.from_agent_id,
                "to_agent_id": result.to_agent_id,
                "trigger": result.trigger,
                "severity": sev_esc,
            },
        ),
        root_dfid=simulation_id,
        agent_id=result.from_agent_id,
        severity="WARNING",
    )
