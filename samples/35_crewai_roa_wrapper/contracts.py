"""
35_crewai_roa_wrapper - Claims Agent Responsibility Contracts.

ClaimsContract defines authority boundaries for customer claims/refunds:
- allowed_refund_categories: product categories agent may propose refunds for
- max_refund_without_escalation: EUR threshold - above requires human approval
- return_window_days: max days from purchase for automatic eligibility

DIR Alignment: ROA Manifesto §3.1 (Responsibility Contract)
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

from dir_core import ResponsibilityContract


@dataclass
class ClaimsContract:
    """
    Claims-specific contract extending ROA pattern.

    Defines what the Claims Agent may propose:
    - Refund categories (e.g., electronics, clothing)
    - Max refund amount without escalation
    - Return window for eligibility

    Load from config.yaml via ClaimsContract.from_config(agent_cfg).
    """

    agent_id: str
    mission: str
    allowed_refund_categories: List[str]
    max_refund_without_escalation: float  # EUR
    return_window_days: int
    allowed_policy_types: List[str]
    role: Literal["STRATEGIST", "EXECUTOR", "MONITOR"] = "EXECUTOR"
    escalate_on_uncertainty: float = 0.7

    @classmethod
    def from_config(cls, agent_cfg: Dict[str, Any]) -> "ClaimsContract":
        """
        Build a ClaimsContract from a parsed config.yaml agent section.

        Expected YAML structure (agent section):
            agent:
              agent_id: "claims_agent_v1"
              mission: "..."
              contract:
                role: EXECUTOR
                allowed_refund_categories: [electronics, clothing, home]
                max_refund_without_escalation: 500.0
                return_window_days: 14
                allowed_policy_types: [REFUND, REPLACE, ESCALATE]
                escalate_on_uncertainty: 0.7  # optional
        """
        contract_cfg = agent_cfg.get("contract", {})
        return cls(
            agent_id=agent_cfg["agent_id"],
            mission=agent_cfg["mission"].strip(),
            allowed_refund_categories=contract_cfg["allowed_refund_categories"],
            max_refund_without_escalation=float(
                contract_cfg["max_refund_without_escalation"]
            ),
            return_window_days=int(contract_cfg["return_window_days"]),
            allowed_policy_types=contract_cfg["allowed_policy_types"],
            role=contract_cfg.get("role", "EXECUTOR"),
            escalate_on_uncertainty=float(
                contract_cfg.get("escalate_on_uncertainty", 0.7)),
        )

    def to_responsibility_contract(self) -> ResponsibilityContract:
        """Convert to standard ResponsibilityContract for DIR integration."""
        return ResponsibilityContract(
            agent_id=self.agent_id,
            role=self.role,
            mission=self.mission,
            authorized_instruments=self.allowed_refund_categories,
            allowed_policy_types=self.allowed_policy_types,
            escalate_on_uncertainty=self.escalate_on_uncertainty,
        )

