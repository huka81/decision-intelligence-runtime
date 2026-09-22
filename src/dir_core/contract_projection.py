"""Normalize canonical and legacy contracts into a Runtime projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .invariant_compile import compile_authority_invariants, invariants_to_transaction_limits
from .models import (
    ContractParameterAmendment,
    ContractReleaseRef,
    InvariantSpec,
    RuntimeContractProjection,
)


def _as_limit(value: Any) -> dict[str, Any] | None:
    """Convert a legacy numeric limit to the projection's typed shape."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"value": float(value)}
    if isinstance(value, Mapping) and "value" in value:
        return dict(value)
    return None


def _is_projection_dump(data: Mapping[str, Any]) -> bool:
    """Detect serialized RuntimeContractProjection payloads."""
    if "release" in data and ("invariants" in data or "transaction_limits" in data):
        return True
    if "agent_id" in data and "invariants" in data and "allowed_policy_types" in data:
        return True
    return False


def _build_projection_from_contract_mapping(data: Mapping[str, Any]) -> RuntimeContractProjection:
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

    invariants = compile_authority_invariants(data)
    transaction_limits = invariants_to_transaction_limits(invariants)

    legacy_limits: dict[str, dict[str, Any]] = {}
    source_limits = dict(authority.get("limits") or {})
    if not source_limits:
        source_limits = {
            key: value
            for key, value in authority.items()
            if key
            not in {
                "allowed_policy_types",
                "authorized_instruments",
                "resource_scope",
                "invariants",
            }
        }
    for key, value in source_limits.items():
        typed_limit = _as_limit(value)
        if typed_limit is not None:
            legacy_limits[str(key)] = typed_limit
    for key, value in legacy_limits.items():
        transaction_limits.setdefault(key, value)

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

    aggregate_raw = governance.get("aggregate_policies") or []
    aggregate_policies = list(aggregate_raw) if isinstance(aggregate_raw, list) else []

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
        transaction_limits=transaction_limits,
        execution_conditions=dict(data.get("execution_conditions") or {}),
        evidence_requirements=evidence,
        escalation_policy=escalation,
        aggregate_policies=aggregate_policies,
        invariants=invariants,
        parameter_amendments=[],
    )


def ensure_projection_invariants(projection: RuntimeContractProjection) -> RuntimeContractProjection:
    """Backfill invariant IR when only legacy projection fields were stored."""
    if projection.invariants:
        return projection
    if (
        not projection.allowed_policy_types
        and not projection.transaction_limits
        and not projection.resource_scope.get("instruments")
        and not projection.execution_conditions
    ):
        return projection

    rebuilt = _build_projection_from_contract_mapping(
        {
            "metadata": projection.release.model_dump(mode="json"),
            "subject": {"agent_id": projection.agent_id, "role": projection.role},
            "mission": {"statement": projection.mission},
            "authority": {
                "allowed_policy_types": projection.allowed_policy_types,
                "resource_scope": projection.resource_scope,
                "limits": projection.transaction_limits,
            },
            "execution_conditions": projection.execution_conditions,
            "responsibility": {"escalation": projection.escalation_policy},
            "governance": {"aggregate_policies": projection.aggregate_policies},
        }
    )
    if not rebuilt.invariants:
        return projection
    data = projection.model_dump(mode="python")
    data["invariants"] = rebuilt.invariants
    data["transaction_limits"] = rebuilt.transaction_limits
    return RuntimeContractProjection.model_validate(data)


def _parse_projection_dump(data: Mapping[str, Any]) -> RuntimeContractProjection:
    payload = dict(data)
    invariants_raw = payload.get("invariants") or []
    payload["invariants"] = [
        spec if isinstance(spec, InvariantSpec) else InvariantSpec.model_validate(spec)
        for spec in invariants_raw
    ]
    amendments_raw = payload.get("parameter_amendments") or []
    payload["parameter_amendments"] = [
        amendment
        if isinstance(amendment, ContractParameterAmendment)
        else ContractParameterAmendment.model_validate(amendment)
        for amendment in amendments_raw
    ]
    if not payload.get("transaction_limits") and payload.get("invariants"):
        payload["transaction_limits"] = invariants_to_transaction_limits(payload["invariants"])
    aggregate_raw = payload.get("aggregate_policies")
    if aggregate_raw is None or isinstance(aggregate_raw, dict):
        payload["aggregate_policies"] = []
    projection = RuntimeContractProjection.model_validate(payload)
    return ensure_projection_invariants(projection)


def project_contract(contract: Mapping[str, Any]) -> RuntimeContractProjection:
    """Create the execution-facing projection from a contract mapping."""
    data = dict(contract)
    if _is_projection_dump(data):
        return _parse_projection_dump(data)
    return ensure_projection_invariants(_build_projection_from_contract_mapping(data))
