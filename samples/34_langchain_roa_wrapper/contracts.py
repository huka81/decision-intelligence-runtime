"""
34_langchain_roa_wrapper - FinOps Agent Responsibility Contracts.

FinOpsContract defines authority boundaries for cloud resource management:
- allowed_environments: instance environments agent may propose actions on (e.g., DEV, STG)
- allowed_policy_types: actions agent may propose (TERMINATE, STOP, SCALE_DOWN)

DIR Alignment: ROA Manifesto §3.1 (Responsibility Contract)
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

from dir import ResponsibilityContract


@dataclass
class FinOpsContract:
    """
    FinOps-specific contract extending ROA pattern.

    allowed_environments restricts which instance environments the agent
    may propose actions on (e.g., ["DEV", "STG"] excludes PROD).

    Load from config.yaml via FinOpsContract.from_config(agent_cfg).
    """

    agent_id: str
    mission: str
    allowed_environments: List[str]
    allowed_policy_types: List[str]
    role: Literal["STRATEGIST", "EXECUTOR", "MONITOR"] = "EXECUTOR"

    @classmethod
    def from_config(cls, agent_cfg: Dict[str, Any]) -> "FinOpsContract":
        """
        Build a FinOpsContract from a parsed config.yaml agent section.

        Expected YAML structure (agent section):
            agent:
              agent_id: "finops_autoscaler_v1"
              mission: "..."
              contract:
                role: EXECUTOR
                allowed_environments: [DEV, STG]
                allowed_policy_types: [TERMINATE, STOP, SCALE_DOWN]
        """
        contract_cfg = agent_cfg.get("contract", {})
        return cls(
            agent_id=agent_cfg["agent_id"],
            mission=agent_cfg["mission"].strip(),
            allowed_environments=contract_cfg["allowed_environments"],
            allowed_policy_types=contract_cfg["allowed_policy_types"],
            role=contract_cfg.get("role", "EXECUTOR"),
        )

    def to_responsibility_contract(self) -> ResponsibilityContract:
        """Convert to standard ResponsibilityContract for DIR integration."""
        return ResponsibilityContract(
            agent_id=self.agent_id,
            role=self.role,
            mission=self.mission,
            authorized_instruments=[],
            allowed_policy_types=self.allowed_policy_types,
        )
