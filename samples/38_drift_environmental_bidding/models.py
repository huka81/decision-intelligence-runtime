"""Pydantic models for environmental (market) bidding drift sample."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class BiddingContract(BaseModel):
    """Responsibility boundary: hard ceiling on CPC (DIM-enforced)."""

    max_cpc_usd: float = Field(gt=0.0, le=100.0)


class SamplePaths(BaseModel):
    database: str = "data/bidding_audit.sqlite"
    inputs_file: str = "data/market_conditions.json"


class AgentConfig(BaseModel):
    agent_id: str = "BiddingAgent"
    agent_version: str = "1.0.0"
    role: str = "EXECUTOR"
    mission: str = ""
    priority: int = 10
    allowed_policy_types: List[str] = Field(
        default_factory=lambda: ["cpc_bid"],
    )


class SimulationConfig(BaseModel):
    """
    Fixture generation metadata — documents how data/market_conditions.json
    was produced. Fields other than ``bid_margin_above_market`` are not used at
    runtime; the pipeline reads the pre-generated JSON directly.
    """

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
    paths: SamplePaths = Field(default_factory=SamplePaths)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    contract: BiddingContract = Field(default_factory=BiddingContract)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    dim: DimConfig = Field(default_factory=DimConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)

    def handshake_contract_dict(self) -> Dict[str, Any]:
        return {
            "role": self.agent.role,
            "mission": self.agent.mission,
            "allowed_policy_types": self.agent.allowed_policy_types,
            "max_cpc_usd": self.contract.max_cpc_usd,
            "ltv_usd": self.monitor.ltv_usd,
            "sample": "38_drift_environmental_bidding",
        }
