"""Pydantic models for retention drift sample (contract + runtime config view)."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class RetentionContract(BaseModel):
    """Responsibility boundary: hard ceiling on discount (DIM-enforced)."""

    max_discount_pct: float = Field(ge=0.0, le=100.0)


class SamplePaths(BaseModel):
    database: str = "data/retention_drift.sqlite"
    inputs_file: str = "data/cancelation.json"


class AgentConfig(BaseModel):
    agent_id: str = "RetentionAgent"
    agent_version: str = "1.0.0"
    role: str = "EXECUTOR"
    mission: str = ""
    priority: int = 0
    allowed_policy_types: List[str] = Field(default_factory=lambda: ["retention_discount"])


class SimulationConfig(BaseModel):
    """Two-phase discount: stable normal window, then accelerating drift + noise."""

    normal_phase_iterations: int = Field(30, ge=0, description="First N decisions: no trend, small spread")
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
    paths: SamplePaths = Field(default_factory=SamplePaths)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    contract: RetentionContract = Field(default_factory=RetentionContract)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    dim: DimConfig = Field(default_factory=DimConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)

    def handshake_contract_dict(self) -> Dict[str, Any]:
        """Payload stored in AgentRegistry JSON contract column."""
        return {
            "role": self.agent.role,
            "mission": self.agent.mission,
            "allowed_policy_types": self.agent.allowed_policy_types,
            "max_discount_pct": self.contract.max_discount_pct,
            "sample": "36_drift_optimization_discount",
        }
