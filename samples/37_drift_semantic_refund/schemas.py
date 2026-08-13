"""Pydantic models and config loading for the semantic refund drift sample."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class RefundContract(BaseModel):
    """Responsibility boundary: hard ceiling on refund amount (DIM-enforced)."""

    max_refund_eur: float = Field(gt=0.0, le=1000.0)


class SamplePaths(BaseModel):
    """Paths relative to the sample directory."""

    inputs_file: str = "data/support_tickets.json"


class AgentConfig(BaseModel):
    agent_id: str = "RefundAgent"
    agent_version: str = "1.0.0"
    role: str = "EXECUTOR"
    mission: str = "Resolve shipping-delay complaints; refunds only if delay exceeds policy hours."
    priority: int = 0
    allowed_policy_types: List[str] = Field(default_factory=lambda: ["REFUND"])


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(
        "run_37_semantic_refund_01",
        description="Correlation id for telemetry (simulation_id on audit rows).",
    )
    seeds: Dict[str, int] = Field(default_factory=dict)
    normal_phase_iterations: int = Field(
        20, ge=0, description="Iterations where agent only refunds if delay > threshold"
    )
    simulation_seed: int = Field(37, description="Seed for tie-breaking / jitter")
    emotional_keywords: List[str] = Field(
        default_factory=lambda: ["ruined", "lawyer", "scandal", "wedding"],
        description="If message contains any (case-insensitive), drift path can refund under threshold",
    )
    refund_amount_compliant_eur: float = Field(35.0, gt=0.0, description="Typical refund when policy allows")
    refund_amount_drift_eur: float = Field(40.0, gt=0.0, description="Typical empathy-biased refund under threshold")


class DimConfig(BaseModel):
    allowed_agents: List[str] = Field(default_factory=list)
    context_state: Dict[str, Any] = Field(default_factory=lambda: {"risk_score": 0.1})


class MonitorConfig(BaseModel):
    window_size: int = Field(20, ge=1)
    violation_rate_threshold: float = Field(0.15, ge=0.0, le=1.0)
    suspension_reason: str = "SEMANTIC_RULE_VIOLATION_DRIFT"
    min_delay_hours_for_refund: float = Field(
        48.0,
        gt=0.0,
        description="Authoritative rule: refund only if delay_hours strictly exceeds this value",
    )


class RegistryConfig(BaseModel):
    supported_versions: str = "1.x"


class RefundSampleConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: SamplePaths = Field(default_factory=SamplePaths)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    contract: RefundContract = Field(default_factory=RefundContract)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    dim: DimConfig = Field(default_factory=DimConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)


def merge_agent_from_agents_list(raw: Dict[str, Any]) -> Dict[str, Any]:
    if raw.get("agent"):
        return raw
    agents = raw.get("agents") or []
    if not agents:
        return raw
    row = agents[0]
    aid = row.get("agent_id")
    if not aid:
        return raw
    c = dict(row.get("contract") or {})
    merged = dict(raw)
    merged["agent"] = {
        "agent_id": aid,
        "agent_version": row.get("agent_version", "1.0.0"),
        "priority": int(row.get("priority", 0)),
        "mission": str(row.get("mission", "")),
        "role": str(c.get("role", "EXECUTOR")),
        "allowed_policy_types": list(c.get("allowed_policy_types", ["REFUND"])),
    }
    limits = dict((c.get("authority") or {}).get("limits") or {})
    if "max_refund_eur" in limits:
        value = limits["max_refund_eur"]
        merged["contract"] = {
            "max_refund_eur": value.get("value", value)
            if isinstance(value, dict)
            else value
        }
    return merged


def load_refund_sample_config(raw: Dict[str, Any]) -> RefundSampleConfig:
    return RefundSampleConfig.model_validate(merge_agent_from_agents_list(raw))


def load_refund_full_config(
    sample_dir: Path,
    *,
    config_filename: str = "config.yaml",
) -> Dict[str, Any]:
    from shared.config import load_yaml_config

    config_path = sample_dir / config_filename
    return load_yaml_config(config_path)


def load_refund_sample_config_bundle(
    sample_dir: Path,
    *,
    config_filename: str = "config.yaml",
) -> RefundSampleConfig:
    merged = load_refund_full_config(sample_dir, config_filename=config_filename)
    return load_refund_sample_config(merged)


__all__ = [
    "AgentConfig",
    "DimConfig",
    "MonitorConfig",
    "RegistryConfig",
    "RefundContract",
    "RefundSampleConfig",
    "SamplePaths",
    "SimulationConfig",
    "load_refund_sample_config",
    "load_refund_full_config",
    "load_refund_sample_config_bundle",
    "merge_agent_from_agents_list",
]
