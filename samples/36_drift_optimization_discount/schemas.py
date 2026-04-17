"""Pydantic models for retention drift sample (domain config slices)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class RetentionContract(BaseModel):
    """Responsibility boundary: hard ceiling on discount (DIM-enforced)."""

    max_discount_pct: float = Field(ge=0.0, le=100.0)


class SamplePaths(BaseModel):
    """Paths relative to the sample directory (anchored by bootstrap for DB elsewhere)."""

    inputs_file: str = "data/cancelation.json"


class AgentConfig(BaseModel):
    agent_id: str = "RetentionAgent"
    agent_version: str = "1.0.0"
    role: str = "EXECUTOR"
    mission: str = ""
    priority: int = 10
    allowed_policy_types: List[str] = Field(default_factory=lambda: ["retention_discount"])


class SimulationConfig(BaseModel):
    """Two-phase discount: stable normal window, then accelerating drift + noise."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(
        "run_36_retention_01",
        description="Correlation id for telemetry (``simulation_id`` on audit rows).",
    )
    seeds: Dict[str, int] = Field(default_factory=dict)
    normal_phase_iterations: int = Field(
        30, ge=0, description="First N decisions: no trend, small spread"
    )
    normal_discount_mean: float = Field(5.5, ge=0.0, le=100.0)
    normal_discount_peak_to_peak_pct: float = Field(
        2.0,
        ge=0.0,
        le=20.0,
        description="Total swing (~1-2pp) around mean in normal phase",
    )
    drift_discount_start_phase2: float = Field(
        6.0,
        ge=0.0,
        description="Discount at first post-normal iteration (curve t=0)",
    )
    drift_discount_end: float = Field(14.2, ge=0.0)
    drift_curve_exponent: float = Field(
        1.7,
        ge=0.5,
        le=5.0,
        description=">1: drift accelerates toward end of run",
    )
    drift_phase_noise_pp: float = Field(
        0.45,
        ge=0.0,
        le=3.0,
        description="Deterministic jitter on the slow drift curve (percentage points)",
    )
    drift_offer_volatility_pp: float = Field(
        1.25,
        ge=0.0,
        le=5.0,
        description=(
            "Extra fast swing around the curve so single offers can sit above or below "
            "the rolling average while the monitor still uses only the window mean"
        ),
    )
    simulation_seed: int = Field(36, description="Seed for reproducible pseudo-random offers")


class DimConfig(BaseModel):
    allowed_agents: List[str] = Field(default_factory=list)
    context_state: Dict[str, Any] = Field(default_factory=lambda: {"risk_score": 0.1})


class MonitorConfig(BaseModel):
    window_size: int = 20
    avg_threshold_pct: float = 10.0
    suspension_reason: str = "PROFITABILITY_DRIFT"


class RegistryConfig(BaseModel):
    supported_versions: str = "1.x"


class RetentionSampleConfig(BaseModel):
    """Domain slice of config.yaml (unknown top-level keys ignored)."""

    model_config = ConfigDict(extra="ignore")

    paths: SamplePaths = Field(default_factory=SamplePaths)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    contract: RetentionContract = Field(default_factory=RetentionContract)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    dim: DimConfig = Field(default_factory=DimConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)


def merge_agent_from_agents_list(raw: Dict[str, Any]) -> Dict[str, Any]:
    """If YAML uses ``agents:`` list only, lift first row into ``agent`` for RetentionSampleConfig."""
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
        "priority": int(row.get("priority", 10)),
        "mission": str(row.get("mission", "")),
        "role": str(c.get("role", "EXECUTOR")),
        "allowed_policy_types": list(c.get("allowed_policy_types", ["retention_discount"])),
    }
    return merged


def load_retention_sample_config(raw: Dict[str, Any]) -> RetentionSampleConfig:
    return RetentionSampleConfig.model_validate(merge_agent_from_agents_list(raw))


def merge_simulation_file_into_config(
    raw: Dict[str, Any],
    *,
    config_yaml_dir: Path,
) -> Dict[str, Any]:
    """Overlay ``simulation`` and ``monitor`` from ``simulation_config`` (default ``simulation.yaml``)."""
    rel = str(raw.get("simulation_config") or "simulation.yaml").strip()
    if not rel:
        return raw
    sim_path = (config_yaml_dir / rel).resolve()
    if not sim_path.is_file():
        return raw
    from shared.config import load_yaml_config

    extra = load_yaml_config(sim_path)
    out = dict(raw)
    if isinstance(extra.get("simulation"), dict):
        out["simulation"] = extra["simulation"]
    if isinstance(extra.get("monitor"), dict):
        out["monitor"] = extra["monitor"]
    return out


def load_retention_full_config(
    sample_dir: Path,
    *,
    config_filename: str = "config.yaml",
) -> Dict[str, Any]:
    """Load ``config.yaml`` and merge the dedicated simulation file when present."""
    from shared.config import load_yaml_config

    config_path = sample_dir / config_filename
    raw = load_yaml_config(config_path)
    return merge_simulation_file_into_config(raw, config_yaml_dir=config_path.parent)


def load_retention_sample_config_bundle(
    sample_dir: Path,
    *,
    config_filename: str = "config.yaml",
) -> RetentionSampleConfig:
    merged = load_retention_full_config(sample_dir, config_filename=config_filename)
    return load_retention_sample_config(merged)


__all__ = [
    "AgentConfig",
    "DimConfig",
    "MonitorConfig",
    "RegistryConfig",
    "RetentionContract",
    "RetentionSampleConfig",
    "SamplePaths",
    "SimulationConfig",
    "load_retention_sample_config",
    "load_retention_full_config",
    "load_retention_sample_config_bundle",
    "merge_agent_from_agents_list",
    "merge_simulation_file_into_config",
]
