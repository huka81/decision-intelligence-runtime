"""Named helpers over ``AuditStore`` / ``decision_audit`` (Sample Guide §9.3–§9.4)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dir_core.storage import AuditStore


def _with_simulation(simulation_id: str, details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(details or {})
    out.setdefault("simulation_id", simulation_id)
    return out


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    *,
    llm_backend: str = "",
    sample: str = "33_insurance_underwriting",
) -> None:
    details: Dict[str, Any] = {"simulation_id": simulation_id, "sample": sample}
    if llm_backend:
        details["llm_backend"] = llm_backend
    audit.record(simulation_id, "SIMULATION_START", details=details)


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    error_message: str = "",
) -> None:
    details: Dict[str, Any] = {"simulation_id": simulation_id, "status": status}
    if error_message:
        details["error_message"] = error_message
    audit.record(simulation_id, "SIMULATION_END", details=details)


def record_underwriting_step(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    event: str,
    *,
    step_id: str = "",
    state: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    audit.record(
        dfid,
        event,
        step_id=step_id,
        state=state,
        details=_with_simulation(simulation_id, details),
    )
