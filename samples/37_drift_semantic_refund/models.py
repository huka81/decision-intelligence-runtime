"""Pydantic models for semantic refund drift sample (contract + runtime config)."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class RefundContract(BaseModel):
    """Responsibility boundary: hard ceiling on refund amount (DIM-enforced)."""

    max_refund_eur: float = Field(gt=0.0, le=1000.0)


class SamplePaths(BaseModel):
    database: str = "data/refund_audit.sqlite"
    inputs_file: str = "data/support_tickets.json"


class AgentConfig(BaseModel):
    agent_id: str = "RefundAgent"
    agent_version: str = "1.0.0"
    role: str = "EXECUTOR"
    mission: str = "Resolve shipping-delay complaints; refunds only if delay exceeds policy hours."
    priority: int = 0
    allowed_policy_types: List[str] = Field(default_factory=lambda: ["REFUND"])


class SimulationConfig(BaseModel):
    """First N tickets: simulated agent follows delay rule; later tickets allow empathy drift."""

    normal_phase_iterations: int = Field(20, ge=0, description="Iterations where agent only refunds if delay > threshold")
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
    paths: SamplePaths = Field(default_factory=SamplePaths)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    contract: RefundContract = Field(default_factory=RefundContract)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    dim: DimConfig = Field(default_factory=DimConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)

    def handshake_contract_dict(self) -> Dict[str, Any]:
        return {
            "role": self.agent.role,
            "mission": self.agent.mission,
            "allowed_policy_types": self.agent.allowed_policy_types,
            "max_refund_eur": self.contract.max_refund_eur,
            "min_delay_hours_for_refund": self.monitor.min_delay_hours_for_refund,
            "sample": "37_drift_semantic_refund",
        }
