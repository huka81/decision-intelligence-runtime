"""Compile canonical contract sugar into declarative invariant IR for DIM."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import InvariantSpec

INV_ALLOWED_POLICY_TYPES = "INV_ALLOWED_POLICY_TYPES"
INV_INSTRUMENT_SCOPE = "INV_INSTRUMENT_SCOPE"
INV_PRICE_SLIPPAGE = "INV_PRICE_SLIPPAGE"
INV_PROHIBITED_INDUSTRIES = "INV_PROHIBITED_INDUSTRIES"

LIMIT_TO_PARAM_FIELD: dict[str, str] = {
    "max_order_size": "params.order_value",
    "max_order_size_usd": "params.order_value",
    "max_transaction_usd": "params.transaction_value",
    "max_discount_pct": "params.discount_pct",
    "max_premium_usd": "params.premium",
    "max_limit_usd": "params.limit_value",
    "max_refund_usd": "params.refund_value",
    "max_drawdown_limit_pct": "params.drawdown_pct",
}


def _limit_field(limit_key: str) -> str:
    return LIMIT_TO_PARAM_FIELD.get(limit_key, f"params.{limit_key.replace('max_', '', 1)}")


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping) and "value" in value:
        try:
            return float(value["value"])
        except (TypeError, ValueError):
            return None
    return None


def _invariant_key(spec: InvariantSpec) -> tuple[str, str]:
    return (spec.type, spec.field)


def _conflicts(existing: list[InvariantSpec], candidate: InvariantSpec) -> bool:
    by_id = {spec.id: spec for spec in existing}
    if candidate.id in by_id:
        return True
    keys = {_invariant_key(spec) for spec in existing}
    return _invariant_key(candidate) in keys


def compile_sugar_invariants(
    authority: Mapping[str, Any],
    execution_conditions: Mapping[str, Any] | None = None,
) -> list[InvariantSpec]:
    """Derive declarative invariants from Bootstrap sugar fields."""
    execution_conditions = dict(execution_conditions or {})
    compiled: list[InvariantSpec] = []

    allowed = list(authority.get("allowed_policy_types") or [])
    if allowed:
        candidate = InvariantSpec(
            id=INV_ALLOWED_POLICY_TYPES,
            type="set",
            field="policy_kind",
            allowed=allowed,
            reason_code="UNAUTHORIZED_POLICY_TYPE",
        )
        if not _conflicts(compiled, candidate):
            compiled.append(candidate)

    instruments = list((authority.get("resource_scope") or {}).get("instruments") or [])
    if instruments:
        candidate = InvariantSpec(
            id=INV_INSTRUMENT_SCOPE,
            type="set",
            field="params.instrument",
            allowed=instruments,
            reason_code="UNAUTHORIZED_INSTRUMENT",
        )
        if not _conflicts(compiled, candidate):
            compiled.append(candidate)

    limits = dict(authority.get("limits") or {})
    if not limits:
        limits = {
            key: value
            for key, value in authority.items()
            if str(key).startswith("max_") and key not in {"max_ceiling"}
        }

    for limit_key, raw_limit in limits.items():
        maximum = _as_float(raw_limit)
        if maximum is None:
            continue
        inv_id = f"INV_LIMIT_{limit_key.upper()}"
        candidate = InvariantSpec(
            id=inv_id,
            type="range",
            field=_limit_field(str(limit_key)),
            max=maximum,
            reason_code="CONTRACT_LIMIT_EXCEEDED",
            runtime_amendable=True,
            min_floor=0.0,
            max_ceiling=maximum,
        )
        if _conflicts(compiled, candidate):
            continue
        compiled.append(candidate)

    prohibited_industries = list(
        (authority.get("exclusions") or {}).get("prohibited_industries") or []
    )
    if prohibited_industries:
        candidate = InvariantSpec(
            id=INV_PROHIBITED_INDUSTRIES,
            type="set",
            field="params.industry",
            denied=prohibited_industries,
            reason_code="PROHIBITED_INDUSTRY",
        )
        if not _conflicts(compiled, candidate):
            compiled.append(candidate)

    slippage = execution_conditions.get("max_price_slippage")
    slippage_pct = _as_float(slippage)
    if slippage_pct is not None:
        candidate = InvariantSpec(
            id=INV_PRICE_SLIPPAGE,
            type="state_match",
            field="params.reference_price",
            snapshot_path="state.price",
            expected=None,
            drift_envelope_pct=slippage_pct,
            reason_code="STALE_PRICE_CONTEXT",
        )
        if not _conflicts(compiled, candidate):
            compiled.append(candidate)

    return compiled


def compile_authority_invariants(
    contract: Mapping[str, Any],
) -> list[InvariantSpec]:
    """Merge explicit authority.invariants with compiled sugar; explicit wins on id conflict."""
    authority = dict(contract.get("authority") or contract.get("permissions") or {})
    execution_conditions = dict(contract.get("execution_conditions") or {})

    explicit_raw = list(authority.get("invariants") or [])
    explicit: list[InvariantSpec] = []
    for entry in explicit_raw:
        if isinstance(entry, InvariantSpec):
            explicit.append(entry)
        elif isinstance(entry, Mapping):
            explicit.append(InvariantSpec.model_validate(dict(entry)))

    sugar = compile_sugar_invariants(authority, execution_conditions)

    merged: list[InvariantSpec] = []
    explicit_ids = {spec.id for spec in explicit}
    explicit_keys = {_invariant_key(spec) for spec in explicit}

    for spec in explicit:
        merged.append(spec)

    for spec in sugar:
        if spec.id in explicit_ids:
            continue
        if _invariant_key(spec) in explicit_keys:
            continue
        merged.append(spec)

    return merged


def invariants_to_transaction_limits(invariants: list[InvariantSpec]) -> dict[str, dict[str, Any]]:
    """Derive legacy transaction_limits view from range invariants."""
    limits: dict[str, dict[str, Any]] = {}
    for spec in invariants:
        if spec.type != "range" or spec.max is None:
            continue
        key = spec.id.removeprefix("INV_LIMIT_").lower() if spec.id.startswith("INV_LIMIT_") else spec.id
        limits[key] = {
            "value": spec.max,
            "metric": spec.field.removeprefix("params.") if spec.field.startswith("params.") else spec.field,
        }
        if spec.min is not None:
            limits[key]["min"] = spec.min
    return limits
