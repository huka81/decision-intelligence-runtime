"""Normalize canonical and legacy contracts into a Runtime projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ContractReleaseRef, RuntimeContractProjection


def _as_limit(value: Any) -> dict[str, Any] | None:
    """Convert a legacy numeric limit to the projection's typed shape."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"value": float(value)}
    if isinstance(value, Mapping) and "value" in value:
        return dict(value)
    return None


def project_contract(contract: Mapping[str, Any]) -> RuntimeContractProjection:
    """Create the execution-facing projection from a contract mapping.

    The adapter accepts the canonical nested shape and the legacy flat shape used
    by the reference samples. It does not interpret arbitrary rule expressions.
    """
    data = dict(contract)
    metadata = dict(data.get("metadata") or {})
    subject = dict(data.get("subject") or {})
    authority = dict(data.get("authority") or {})
    responsibility = dict(data.get("responsibility") or {})
    governance = dict(data.get("governance") or {})

    legacy_permissions = dict(data.get("permissions") or {})
    if not authority and legacy_permissions:
        authority = legacy_permissions
    if not authority and (
        "allowed_policy_types" in data or "authorized_instruments" in data
    ):
        authority = {
            key: value
            for key, value in data.items()
            if key in {"allowed_policy_types", "authorized_instruments"}
            or key.startswith("max_")
        }

    release = ContractReleaseRef(
        contract_id=str(metadata.get("contract_id", data.get("contract_id", "legacy"))),
        contract_version=str(metadata.get("version", data.get("version", "0.0.0"))),
        api_version=str(metadata.get("api_version", data.get("api_version", "legacy"))),
        contract_hash=str(metadata.get("contract_hash", data.get("contract_hash", ""))),
    )

    limits: dict[str, dict[str, Any]] = {}
    source_limits = dict(authority.get("limits") or {})
    if not source_limits:
        source_limits = {
            key: value
            for key, value in authority.items()
            if key not in {"allowed_policy_types", "authorized_instruments", "resource_scope"}
        }
    for key, value in source_limits.items():
        typed_limit = _as_limit(value)
        if typed_limit is not None:
            limits[str(key)] = typed_limit

    evidence = dict(responsibility.get("evidence") or {})
    if not evidence and "evidence_level" in responsibility:
        evidence["level"] = responsibility["evidence_level"]

    escalation = dict(responsibility.get("escalation") or {})
    if not escalation:
        if "escalation" in responsibility:
            escalation["mode"] = responsibility["escalation"]
        if "escalate_on_uncertainty" in responsibility:
            escalation["confidence_below"] = responsibility["escalate_on_uncertainty"]

    mission_value = data.get("mission", "")
    if isinstance(mission_value, Mapping):
        mission_value = mission_value.get("statement", "")

    return RuntimeContractProjection(
        release=release,
        agent_id=str(subject.get("agent_id", data.get("agent_id", ""))),
        role=subject.get("role", data.get("role", "EXECUTOR")),
        mission=str(mission_value),
        allowed_policy_types=list(
            authority.get("allowed_policy_types")
            or legacy_permissions.get("allowed_policy_types")
            or []
        ),
        resource_scope=dict(authority.get("resource_scope") or {}),
        transaction_limits=limits,
        execution_conditions=dict(data.get("execution_conditions") or {}),
        evidence_requirements=evidence,
        escalation_policy=escalation,
        aggregate_policies=list(governance.get("aggregate_policies") or []),
    )
