"""Canonical contract model used by the finance-trading reference sample."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FinanceContract(BaseModel):
    """Small native view of the canonical contract used by this sample."""

    api_version: str = "roa.dir/v1"
    kind: str = "ResponsibilityContract"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    subject: Dict[str, Any] = Field(default_factory=dict)
    mission: str = ""
    authority: Dict[str, Any] = Field(default_factory=dict)
    execution_conditions: Dict[str, Any] = Field(default_factory=dict)
    responsibility: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, contract: Mapping[str, Any]) -> "FinanceContract":
        """Validate the canonical contract stored in sample configuration."""
        return cls.model_validate(dict(contract))

    @property
    def agent_id(self) -> str:
        return str(self.subject.get("agent_id", ""))

    @property
    def role(self) -> str:
        return str(self.subject.get("role", "EXECUTOR"))

    @property
    def parent_agent_id(self) -> Optional[str]:
        value = self.subject.get("parent_agent_id")
        return str(value) if value is not None else None

    @property
    def authorized_instruments(self) -> List[str]:
        scope = self.authority.get("resource_scope") or {}
        return list(scope.get("instruments") or [])

    @property
    def allowed_policy_types(self) -> List[str]:
        return list(self.authority.get("allowed_policy_types") or [])

    @property
    def escalate_on_uncertainty(self) -> float:
        escalation = self.responsibility.get("escalation") or {}
        return float(escalation.get("confidence_below", 0.7))

    @property
    def wake_up_threshold_pct(self) -> float:
        return float(self.execution_conditions.get("wake_up_threshold_pct", 0.5))

    def limit(self, name: str, default: float) -> float:
        """Read a named canonical authority limit."""
        limits = self.authority.get("limits") or {}
        value = limits.get(name, default)
        if isinstance(value, Mapping):
            value = value.get("value", default)
        return float(value)

    @property
    def max_drawdown_limit(self) -> float:
        return self.limit("max_drawdown_limit", 0.02)

    @property
    def take_profit_pct(self) -> float:
        return self.limit("take_profit_pct", 0.015)

    @property
    def max_exposure(self) -> float:
        return self.limit("max_exposure", 10000.0)

    @property
    def reduce_pct(self) -> float:
        return self.limit("reduce_pct", 0.5)
