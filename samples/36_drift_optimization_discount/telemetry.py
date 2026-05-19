"""Map domain steps to ``bundle.decision_audit.record`` / ``decision_audit_events``.

Aligned with ``src/dir_core/storage/schema.sql`` and
``.cursor/rules/07-telemetry-guidelines.md``:

* ``root_dfid`` = ``simulation_id`` on every row (run lineage); per-decision ``dfid``
  remains the execution identifier.
* ``detail_json`` includes ``correlation_id`` (= ``simulation_id``).
* ``step_id`` / ``state`` / ``severity`` use first-class columns.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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
    dfid: str,
    simulation_id: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    details = _detail_base(simulation_id, extra)
    aid = (extra or {}).get("agent_id")
    if isinstance(aid, str) and aid:
        agent_kw: Dict[str, Any] = {"agent_id": aid}
    else:
        agent_kw = {}
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=details,
        root_dfid=simulation_id,
        severity="INFO",
        **agent_kw,
    )


def record_simulation_end(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    status: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"status": status, **(extra or {})}
    sev = "ERROR" if status.lower() == "error" else "INFO"
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_END",
        step_id="SIMULATION",
        state=status.upper(),
        details=_detail_base(simulation_id, payload),
        root_dfid=simulation_id,
        severity=sev,
    )


def record_context_compiled(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    input_ref: str,
    session_keys: list,
    plan: str = "",
    channel: str = "",
    user_reason: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CONTEXT_COMPILED",
        step_id="CONTEXT_COMPILED",
        state="READY",
        details=_detail_base(
            simulation_id,
            {
                "input_ref": input_ref,
                "session_keys": session_keys,
                "plan": plan,
                "channel": channel,
                "user_reason": user_reason,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_policy_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    discount_offered: float,
    policy_kind: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "POLICY_PROPOSAL",
        step_id="POLICY_PROPOSAL",
        state="EMITTED",
        details=_detail_base(
            simulation_id,
            {"discount_offered": discount_offered, "policy_kind": policy_kind},
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_dim_validation(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    verdict: str,
    reason: str,
) -> None:
    v_upper = str(verdict).upper()
    sev = "INFO"
    if v_upper in ("REJECT", "ROA_FAIL", "ESCALATE"):
        sev = "WARNING"
    bundle.decision_audit.record(
        dfid,
        "DIM_VALIDATION",
        step_id="DIM_VALIDATION",
        state=v_upper,
        details=_detail_base(simulation_id, {"reason": reason}),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )


def record_retention_executed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    discount_offered: float,
    policy_kind: str,
    proposal_dump: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "RETENTION_EXECUTED",
        step_id="RETENTION_EXECUTED",
        state="COMPLETED",
        details=_detail_base(
            simulation_id,
            {
                "discount_offered": discount_offered,
                "policy_kind": policy_kind,
                "proposal": proposal_dump,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_monitor_tick(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    state: str,
    moving_avg_discount_pct: float,
    window_size: int,
    threshold_pct: float,
) -> None:
    st = str(state).upper()
    sev = "WARNING" if st == "ALERT" else "INFO"
    bundle.decision_audit.record(
        dfid,
        "MONITOR_TICK",
        step_id="MONITOR_TICK",
        state=st,
        details=_detail_base(
            simulation_id,
            {
                "moving_avg_discount_pct": round(moving_avg_discount_pct, 4),
                "window_size": window_size,
                "threshold_pct": threshold_pct,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )


def record_agent_suspended(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    moving_avg_discount_pct: float,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "AGENT_SUSPENDED",
        step_id="AGENT_SUSPENDED",
        state="SUSPENDED",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "reason": reason,
                "moving_avg_discount_pct": round(moving_avg_discount_pct, 4),
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING",
    )


def record_agent_decision_summary(
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
    explain_narrative: str,
) -> None:
    v_upper = str(verdict).upper()
    sev = "INFO"
    if v_upper in ("REJECT", "ESCALATE", "ROA_FAIL"):
        sev = "WARNING"
    bundle.decision_audit.record(
        dfid,
        "AGENT_DECISION",
        step_id="ROA_DIM",
        state=v_upper,
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "policy_kind": policy_kind,
                "verdict": verdict,
                "reason": str(reason),
                "confidence": confidence,
                "justification": justification,
                "explain_narrative": explain_narrative,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )
