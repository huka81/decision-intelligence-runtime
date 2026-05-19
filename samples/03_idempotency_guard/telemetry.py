"""``AuditStore`` helpers for ``decision_audit_events`` (DIR §7).

Aligned with ``src/dir_core/storage/schema.sql`` and
``.cursor/rules/07-telemetry-guidelines.md``:

* ``root_dfid`` = ``simulation_id`` for the demo; each row uses the decision-flow
  ``dfid``.
* ``detail_json`` includes ``correlation_id``.
* Idempotency outcomes use stable ``event_type`` values and structured payloads.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from dir_core.storage.base import AuditStore

DEMO_AGENT_ID = "idempotency_demo_v1"


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
    simulation_id: str,
    *,
    sample: str = "03_idempotency_guard",
) -> None:
    audit.record(
        simulation_id,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=_detail_base(
            simulation_id,
            {"sample": sample, "topic": "idempotency_guard"},
        ),
        root_dfid=simulation_id,
        agent_id=DEMO_AGENT_ID,
        severity="INFO",
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
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


def record_idempotency_outcome(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    op_step_id: str,
    cache_hit: bool,
    idempotency_key_prefix: str,
    duration_sec: float,
    params_summary: Dict[str, Any],
) -> None:
    event = "IDEMPOTENCY_CACHE_HIT" if cache_hit else "IDEMPOTENCY_CACHE_MISS"
    state = "CACHED" if cache_hit else "EXECUTED"
    audit.record(
        dfid,
        event,
        step_id=op_step_id,
        state=state,
        details=_detail_base(
            simulation_id,
            {
                "idempotency_key_prefix": idempotency_key_prefix,
                "cache_hit": cache_hit,
                "duration_sec": round(duration_sec, 6),
                "params": params_summary,
            },
        ),
        root_dfid=simulation_id,
        agent_id=DEMO_AGENT_ID,
        severity="INFO",
    )
