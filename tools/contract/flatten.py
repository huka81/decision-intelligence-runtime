"""Flatten canonical nested contracts to dir_core flat ResponsibilityContract dicts."""

from __future__ import annotations

from typing import Any, Dict

from .schema import CanonicalContract, IRREVERSIBLE_LIMIT_KEYS

_DIR_CORE_ROLES = frozenset({"STRATEGIST", "EXECUTOR", "MONITOR"})


def _map_role_for_dir_core(role: str) -> str:
    """Map canonical roles to dir_core ContractRole values (no INTERFACE in kernel)."""
    if role in _DIR_CORE_ROLES:
        return role
    return "EXECUTOR"


def _normalize_drawdown_fraction(pct_or_fraction: float) -> float:
    """Convert canonical max_drawdown_limit_pct to dir_core fraction."""
    if pct_or_fraction > 1.0:
        return pct_or_fraction / 100.0
    return pct_or_fraction


def flatten_canonical(contract: CanonicalContract | Dict[str, Any]) -> Dict[str, Any]:
    """
    Map nested Manifesto contract to flat dict compatible with dir_core.ResponsibilityContract.

    Convention: canonical ``max_drawdown_limit_pct`` uses percent points (e.g. 4.0 = 4%);
    dir_core ``max_drawdown_limit`` uses a fraction (e.g. 0.04).
    """
    if isinstance(contract, CanonicalContract):
        data = contract.model_dump()
    else:
        data = dict(contract)

    authority = dict(data.get("authority") or {})
    responsibility = dict(data.get("responsibility") or {})

    flat: Dict[str, Any] = {
        "agent_id": data["agent_id"],
        "role": _map_role_for_dir_core(data.get("role", "EXECUTOR")),
        "mission": data.get("mission", ""),
        "authorized_instruments": list(authority.get("authorized_instruments") or []),
        "allowed_policy_types": list(authority.get("allowed_policy_types") or []),
        "escalate_on_uncertainty": float(
            responsibility.get("escalate_on_uncertainty", 0.7)
        ),
    }

    drawdown = authority.get("max_drawdown_limit_pct")
    if drawdown is not None:
        flat["max_drawdown_limit"] = _normalize_drawdown_fraction(float(drawdown))

    permissions: Dict[str, float] = {}
    for key in IRREVERSIBLE_LIMIT_KEYS:
        value = authority.get(key)
        if isinstance(value, (int, float)) and value > 0:
            permissions[key] = float(value)

    extra_authority = {
        k: v
        for k, v in authority.items()
        if k not in {
            "authorized_instruments",
            "allowed_policy_types",
            "max_drawdown_limit_pct",
            *IRREVERSIBLE_LIMIT_KEYS,
        }
        and isinstance(v, (int, float))
        and v > 0
    }
    permissions.update({k: float(v) for k, v in extra_authority.items()})

    if permissions:
        flat["permissions"] = permissions

    return flat


def flatten_contract_dict(contract_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    If contract_dict uses nested authority/responsibility, flatten it.
    Otherwise return a shallow copy unchanged.
    """
    if "authority" not in contract_dict:
        return dict(contract_dict)

    nested = dict(contract_dict)
    if "agent_id" not in nested and "agent_id" in contract_dict:
        nested["agent_id"] = contract_dict["agent_id"]
    return flatten_canonical(nested)


def inflate_flat_to_canonical(flat: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort reverse mapping from flat sample config to canonical nested dict."""
    permissions = dict(flat.get("permissions") or {})
    authority: Dict[str, Any] = {
        "authorized_instruments": list(flat.get("authorized_instruments") or []),
        "allowed_policy_types": list(flat.get("allowed_policy_types") or []),
    }

    for key in IRREVERSIBLE_LIMIT_KEYS:
        if key in flat and flat[key] is not None:
            authority[key] = flat[key]
        elif key in permissions:
            authority[key] = permissions[key]

    drawdown = flat.get("max_drawdown_limit")
    if drawdown is not None and "max_drawdown_limit_pct" not in authority:
        fraction = float(drawdown)
        authority["max_drawdown_limit_pct"] = (
            fraction * 100.0 if fraction <= 1.0 else fraction
        )

    return {
        "agent_id": flat.get("agent_id", "unknown_agent"),
        "version": flat.get("version", "1.0.0"),
        "owner": flat.get("owner", "owner@example.com"),
        "role": flat.get("role", "EXECUTOR"),
        "mission": flat.get("mission", ""),
        "authority": authority,
        "responsibility": {
            "explainability": flat.get("explainability", "required"),
            "evidence_level": flat.get("evidence_level", "medium"),
            "escalation": flat.get("escalation", "mandatory"),
            "escalate_on_uncertainty": float(flat.get("escalate_on_uncertainty", 0.7)),
            "aggregate_thresholds": dict(flat.get("aggregate_thresholds") or {}),
        },
    }
