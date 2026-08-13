"""Seed interview answers from existing sample config.yaml files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .flatten import flatten_canonical, inflate_flat_to_canonical
from .presets import PRESETS
from .schema import CanonicalContract, InterviewAnswers, IRREVERSIBLE_LIMIT_KEYS


def _guess_preset(sample_path: Path, flat: Dict[str, Any]) -> str:
    name = sample_path.name.lower()
    parent = sample_path.parent.name.lower()
    policy_types = set(flat.get("allowed_policy_types") or [])

    if "fraud" in parent or policy_types & {"ALLOW", "BLOCK", "CHALLENGE"}:
        return "fraud_gate"
    if "refund" in parent or "REFUND" in policy_types:
        return "retention_refund"
    if "underwriting" in parent or "insurance" in parent:
        return "underwriting"
    if policy_types & {"BUY", "SELL", "HOLD", "CLOSE_POSITION"}:
        return "trading"
    if "trading" in parent or "finance" in parent or "quick_start" in parent:
        return "trading"
    if flat.get("role") == "INTERFACE":
        return "interface_dmz"
    if flat.get("role") == "MONITOR":
        return "monitor"
    if flat.get("role") == "STRATEGIST":
        return "strategist"
    return "generic"


def _extract_flat_contract(config: Dict[str, Any], agent_id: Optional[str]) -> Dict[str, Any]:
    if "agents" in config:
        agents = config["agents"]
        if not agents:
            raise ValueError("config has empty agents list")
        if agent_id:
            for entry in agents:
                if entry.get("agent_id") == agent_id:
                    flat = dict(entry.get("contract") or {})
                    flat["agent_id"] = agent_id
                    if entry.get("mission") and not flat.get("mission"):
                        flat["mission"] = entry["mission"]
                    return flat
            raise ValueError(f"agent_id '{agent_id}' not found in config agents")
        entry = agents[0]
        aid = entry.get("agent_id", "unknown_agent")
        flat = dict(entry.get("contract") or {})
        flat["agent_id"] = aid
        if entry.get("mission") and not flat.get("mission"):
            flat["mission"] = entry["mission"]
        return flat

    if "contract" in config:
        flat = dict(config["contract"])
        flat.setdefault("agent_id", flat.get("agent_id", "unknown_agent"))
        return flat

    raise ValueError("config.yaml has no 'contract' or 'agents' block")


def _limits_from_flat(flat: Dict[str, Any]) -> Dict[str, float]:
    limits: Dict[str, float] = {}
    permissions = flat.get("permissions") or {}
    for key in IRREVERSIBLE_LIMIT_KEYS:
        if key in flat and flat[key] is not None:
            limits[key] = float(flat[key])
        elif key in permissions:
            limits[key] = float(permissions[key])

    drawdown = flat.get("max_drawdown_limit")
    if drawdown is not None and "max_drawdown_limit_pct" not in limits:
        fraction = float(drawdown)
        limits["max_drawdown_limit_pct"] = (
            fraction * 100.0 if fraction <= 1.0 else fraction
        )
    return limits


def answers_from_sample(
    sample_dir: str | Path,
    agent_id: Optional[str] = None,
) -> InterviewAnswers:
    """Build InterviewAnswers from samples/<NN>_<use_case>/config.yaml."""
    sample_path = Path(sample_dir)
    config_path = sample_path / "config.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"config.yaml not found: {config_path}")

    with open(config_path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    flat = _extract_flat_contract(config, agent_id)
    canonical_data = (
        CanonicalContract.from_raw(flat).model_dump(exclude_none=True)
        if "api_version" in flat or "metadata" in flat or "subject" in flat
        else inflate_flat_to_canonical(flat)
    )
    canonical = CanonicalContract.from_raw(canonical_data)
    runtime_flat = flatten_canonical(canonical)
    preset = _guess_preset(sample_path, runtime_flat)

    preset_def = PRESETS.get(preset, PRESETS["generic"])
    limits = canonical.authority.numeric_limits()
    if not limits:
        limits = dict(preset_def.suggested_limits)

    return InterviewAnswers(
        preset=preset,
        agent_id=canonical.agent_id,
        owner=canonical.owner,
        role=canonical.role,
        mission=canonical.mission.statement or preset_def.mission_template,
        allowed_policy_types=canonical.authority.allowed_policy_types
        or list(preset_def.allowed_policy_types),
        authorized_instruments=canonical.authority.authorized_instruments
        or list(preset_def.authorized_instruments),
        irreversible_limits=limits,
        limit_units={
            key: limit.unit for key, limit in canonical.authority.limits.items()
        },
        explainability=canonical.responsibility.explainability,
        evidence_level=canonical.responsibility.evidence.level,
        escalation=canonical.responsibility.escalation.mode,
        escalate_on_uncertainty=canonical.responsibility.escalation.confidence_below,
        version="1.0.0",
    )
