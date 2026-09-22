"""Apply human-gated parameter amendments to runtime contract projections."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import (
    ContractParameterAmendment,
    InvariantSpec,
    RuntimeContractProjection,
)

ALLOWED_PATCH_KEYS = frozenset({"min", "max", "allowed", "drift_envelope_pct"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def apply_amendment_patch(
    invariant: InvariantSpec,
    patch: dict[str, Any],
) -> InvariantSpec:
    """Return a copy of invariant with scalar patch applied."""
    data = invariant.model_dump()
    for key, value in patch.items():
        data[key] = value
    return InvariantSpec.model_validate(data)


def validate_amendment_patch(
    invariant: InvariantSpec,
    patch: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str | None:
    """Validate amendment patch against runtime_amendable rules and envelope."""
    now = now or _utcnow()
    if not invariant.runtime_amendable:
        return "INVARIANT_NOT_AMENDABLE"

    if not patch:
        return "EMPTY_PATCH"

    invalid_keys = set(patch) - ALLOWED_PATCH_KEYS
    if invalid_keys:
        return f"DISALLOWED_PATCH_KEYS: {sorted(invalid_keys)}"

    if "max" in patch and patch["max"] is not None:
        new_max = float(patch["max"])
        if invariant.max_ceiling is not None and new_max > float(invariant.max_ceiling):
            return "PATCH_EXCEEDS_MAX_CEILING"
        if invariant.min_floor is not None and new_max < float(invariant.min_floor):
            return "PATCH_BELOW_MIN_FLOOR"

    if "min" in patch and patch["min"] is not None:
        new_min = float(patch["min"])
        if invariant.min_floor is not None and new_min < float(invariant.min_floor):
            return "PATCH_BELOW_MIN_FLOOR"
        if invariant.max_ceiling is not None and new_min > float(invariant.max_ceiling):
            return "PATCH_EXCEEDS_MAX_CEILING"

    if "allowed" in patch:
        new_allowed = list(patch["allowed"])
        if not isinstance(patch["allowed"], list):
            return "ALLOWED_PATCH_MUST_BE_LIST"
        signed_allowed = set(invariant.allowed)
        if signed_allowed and not set(new_allowed).issubset(signed_allowed):
            return "ALLOWED_PATCH_EXPANSION_FORBIDDEN"
        if not signed_allowed and invariant.type == "set":
            return "ALLOWED_PATCH_REQUIRES_SIGNED_BASE"

    if "drift_envelope_pct" in patch and patch["drift_envelope_pct"] is not None:
        new_drift = float(patch["drift_envelope_pct"])
        if new_drift < 0:
            return "DRIFT_ENVELOPE_NEGATIVE"

    if invariant.amend_ttl_seconds is not None and invariant.amend_ttl_seconds <= 0:
        return "INVALID_AMEND_TTL"

    return None


def resolve_expires_at(
    amendment: ContractParameterAmendment,
    invariant: InvariantSpec,
) -> datetime | None:
    if amendment.expires_at is not None:
        return amendment.expires_at
    if invariant.amend_ttl_seconds:
        return amendment.created_at + timedelta(seconds=int(invariant.amend_ttl_seconds))
    return None


def effective_invariants(
    projection: RuntimeContractProjection,
    *,
    now: datetime | None = None,
) -> list[InvariantSpec]:
    """Merge base invariants with active parameter amendments."""
    now = now or _utcnow()
    by_id = {spec.id: spec for spec in projection.invariants}

    for amendment in projection.parameter_amendments:
        expires_at = resolve_expires_at(amendment, by_id.get(amendment.invariant_id, InvariantSpec(
            id=amendment.invariant_id,
            type="range",
            field="policy_kind",
        )))
        if expires_at is not None and now >= expires_at:
            continue
        base = by_id.get(amendment.invariant_id)
        if base is None:
            continue
        by_id[amendment.invariant_id] = apply_amendment_patch(base, amendment.patch)

    return list(by_id.values())


def projection_with_effective_invariants(
    projection: RuntimeContractProjection,
    *,
    now: datetime | None = None,
) -> RuntimeContractProjection:
    """Return projection copy whose invariants reflect active amendments."""
    effective = effective_invariants(projection, now=now)
    data = projection.model_dump(mode="python")
    data["invariants"] = effective
    data["transaction_limits"] = _limits_from_invariants(effective)
    return RuntimeContractProjection.model_validate(data)


def _limits_from_invariants(invariants: list[InvariantSpec]) -> dict[str, dict[str, Any]]:
    from .invariant_compile import invariants_to_transaction_limits

    return invariants_to_transaction_limits(invariants)
