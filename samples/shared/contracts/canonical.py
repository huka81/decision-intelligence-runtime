"""Canonical sample contract loading compatibility helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict


def canonical_contract_to_runtime(
    contract: Mapping[str, Any], agent_id: str
) -> Dict[str, Any]:
    """Project canonical sample contracts to the current Runtime model shape.

    This compatibility boundary is used only by samples whose application code
    still consumes the shared flat Runtime model. Reference samples with native
    canonical models should read their contract directly instead.
    """
    data = dict(contract)
    metadata = dict(data.get("metadata") or {})
    subject = dict(data.get("subject") or {})
    authority = dict(data.get("authority") or {})
    responsibility = dict(data.get("responsibility") or {})
    evidence = dict(responsibility.get("evidence") or {})
    escalation = dict(responsibility.get("escalation") or {})

    mission = data.get("mission", "")
    if isinstance(mission, Mapping):
        mission = mission.get("statement", "")

    resource_scope = dict(authority.get("resource_scope") or {})
    authorized_instruments = list(
        authority.get("authorized_instruments")
        or resource_scope.get("instruments")
        or resource_scope.get("categories")
        or []
    )
    runtime: Dict[str, Any] = {
        "agent_id": subject.get("agent_id", data.get("agent_id", agent_id)),
        "role": subject.get("role", data.get("role", "EXECUTOR")),
        "mission": str(mission),
        "authorized_instruments": authorized_instruments,
        "allowed_policy_types": list(authority.get("allowed_policy_types") or []),
        "escalate_on_uncertainty": escalation.get(
            "confidence_below",
            responsibility.get("escalate_on_uncertainty", 0.7),
        ),
        "parent_agent_id": subject.get(
            "parent_agent_id", data.get("parent_agent_id")
        ),
        "version": metadata.get("version", data.get("version", "1.0.0")),
    }

    for key, value in dict(authority.get("limits") or {}).items():
        runtime[key] = value.get("value", value) if isinstance(value, Mapping) else value

    exclusions = dict(authority.get("exclusions") or {})
    if "prohibited_industries" in exclusions:
        runtime["prohibited_industries"] = list(exclusions["prohibited_industries"])

    execution_conditions = dict(data.get("execution_conditions") or {})
    if "environments" in resource_scope:
        runtime["allowed_environments"] = list(resource_scope["environments"])
    if "wake_up_threshold_pct" in execution_conditions:
        runtime["wake_up_threshold_pct"] = execution_conditions[
            "wake_up_threshold_pct"
        ]
    elif "wake_up_threshold_pct" in data:
        runtime["wake_up_threshold_pct"] = data["wake_up_threshold_pct"]

    return runtime
