"""Claims domain contract loaded beside ``ResponsibilityContract`` (ROA §3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from dir_core import ResponsibilityContract


@dataclass
class ClaimsContract:
    """Authority boundaries for refund proposals validated in Kernel Space."""

    agent_id: str
    mission: str
    allowed_refund_categories: List[str]
    max_refund_without_escalation: float
    return_window_days: int
    allowed_policy_types: List[str]
    role: str = "EXECUTOR"
    escalate_on_uncertainty: float = 0.7

    @classmethod
    def from_agent_row(cls, row: Dict[str, Any], rc: ResponsibilityContract) -> "ClaimsContract":
        bounds = row.get("claims_bounds") or {}
        if "max_refund_without_escalation" not in bounds or "return_window_days" not in bounds:
            raise ValueError("agents[].claims_bounds requires max_refund_without_escalation and return_window_days")
        return cls(
            agent_id=rc.agent_id,
            mission=str(row.get("mission") or rc.mission or "").strip(),
            allowed_refund_categories=list(rc.authorized_instruments),
            max_refund_without_escalation=float(bounds["max_refund_without_escalation"]),
            return_window_days=int(bounds["return_window_days"]),
            allowed_policy_types=list(rc.allowed_policy_types),
            role=str(rc.role.value if hasattr(rc.role, "value") else rc.role),
            escalate_on_uncertainty=float(rc.escalate_on_uncertainty),
        )

    def to_responsibility_contract(self) -> ResponsibilityContract:
        return ResponsibilityContract(
            agent_id=self.agent_id,
            role=self.role,  # type: ignore[arg-type]
            mission=self.mission,
            authorized_instruments=list(self.allowed_refund_categories),
            allowed_policy_types=self.allowed_policy_types,
            escalate_on_uncertainty=self.escalate_on_uncertainty,
        )
