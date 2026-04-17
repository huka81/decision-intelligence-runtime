"""Domain config and helpers for the environmental bidding drift sample."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from dir_core import ResponsibilityContract


class SamplePaths(BaseModel):
    inputs_file: str = "data/market_conditions.json"


class SimulationConfig(BaseModel):
    """
    ``run_id`` and ``seeds`` group telemetry; other fields document fixture generation
    for ``data/market_conditions.json`` (not read at runtime).
    """

    run_id: str = "bidding_drift_38"
    seeds: Dict[str, int] = Field(default_factory=lambda: {"market": 38})
    normal_phase_iterations: int = Field(30, ge=0)
    market_cpc_start: float = Field(1.20, gt=0.0)
    market_cpc_end: float = Field(1.98, gt=0.0)
    market_cpc_noise_pp: float = Field(0.02, ge=0.0)
    simulation_seed: int = Field(38, ge=0)
    bid_margin_above_market: float = Field(0.02, ge=0.0)


class DimConfig(BaseModel):
    allowed_agents: List[str] = Field(default_factory=list)
    context_state: Dict[str, Any] = Field(
        default_factory=lambda: {"risk_score": 0.1},
    )


class MonitorConfig(BaseModel):
    window_size: int = Field(10, ge=1)
    ltv_usd: float = Field(1.80, gt=0.0)
    negative_roi_consecutive_cycles: int = Field(5, ge=1)
    suspension_reason: str = "NEGATIVE_ROI_ENVIRONMENTAL_DRIFT"


class RegistryConfig(BaseModel):
    supported_versions: str = "1.x"


class BiddingSampleConfig(BaseModel):
    """Typed slices of ``config.yaml`` (extras such as ``database`` are ignored here)."""

    model_config = ConfigDict(extra="ignore")

    paths: SamplePaths = Field(default_factory=SamplePaths)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    dim: DimConfig = Field(default_factory=DimConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)


def max_cpc_ceiling_usd(contract: ResponsibilityContract) -> float:
    """In this sample, ``max_drawdown_limit`` encodes the DIM-enforced CPC ceiling (USD)."""
    return float(contract.max_drawdown_limit)
