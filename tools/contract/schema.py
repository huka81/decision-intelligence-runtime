"""Canonical Manifesto-aligned Responsibility Contract schema."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

ContractRoleLiteral = Literal["STRATEGIST", "EXECUTOR", "MONITOR", "INTERFACE"]
ExplainabilityLiteral = Literal["required", "optional"]
EvidenceLevelLiteral = Literal["high", "medium", "low"]
EscalationLiteral = Literal["mandatory", "conditional", "disabled"]

# Numeric authority limits used for Bootstrap validation and flatten permissions.
IRREVERSIBLE_LIMIT_KEYS: tuple[str, ...] = (
    "max_order_size_usd",
    "max_drawdown_limit_pct",
    "max_transaction_usd",
    "max_premium_usd",
    "max_limit_usd",
    "max_refund_usd",
    "max_discount_pct",
)

# Common LLM / human aliases → canonical irreversible limit keys.
LIMIT_KEY_ALIASES: Dict[str, str] = {
    "max_discount_percentage": "max_discount_pct",
    "max_discount_percent": "max_discount_pct",
    "max_discount": "max_discount_pct",
    "discount_pct": "max_discount_pct",
    "discount_percentage": "max_discount_pct",
    "max_order_size": "max_order_size_usd",
    "max_order_usd": "max_order_size_usd",
    "max_drawdown": "max_drawdown_limit_pct",
    "max_drawdown_pct": "max_drawdown_limit_pct",
    "max_drawdown_limit": "max_drawdown_limit_pct",
    "max_transaction": "max_transaction_usd",
    "max_txn_usd": "max_transaction_usd",
    "max_premium": "max_premium_usd",
    "max_coverage_limit": "max_limit_usd",
    "max_refund": "max_refund_usd",
    "max_refund_eur": "max_refund_usd",
}


def normalize_limit_key(key: str) -> str:
    """Map alias limit names to canonical IRREVERSIBLE_LIMIT_KEYS."""
    return LIMIT_KEY_ALIASES.get(key, key)


def normalize_contract_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize LLM/human contract shapes into the canonical nested schema.

    Handles:
    - ``authority.irreversible_limits`` nested map → flat authority limit fields
    - alias keys (e.g. ``max_discount_percentage`` → ``max_discount_pct``)
    """
    out = dict(data)
    authority = dict(out.get("authority") or {})

    nested = authority.pop("irreversible_limits", None)
    if isinstance(nested, dict):
        for key, value in nested.items():
            canon = normalize_limit_key(str(key))
            if canon not in authority or authority[canon] is None:
                authority[canon] = value

    # Rename alias keys already at authority top-level.
    renamed: Dict[str, Any] = {}
    drop: List[str] = []
    for key, value in list(authority.items()):
        if key in {"authorized_instruments", "allowed_policy_types"}:
            continue
        canon = normalize_limit_key(str(key))
        if canon != key:
            if canon not in authority or authority[canon] is None:
                renamed[canon] = value
            drop.append(key)
    for key in drop:
        authority.pop(key, None)
    authority.update(renamed)

    out["authority"] = authority
    return out


class AuthoritySpec(BaseModel):
    """Deterministic boundaries enforced by DIM in Kernel Space."""

    authorized_instruments: List[str] = Field(default_factory=list)
    allowed_policy_types: List[str] = Field(default_factory=list)
    max_order_size_usd: Optional[float] = None
    max_drawdown_limit_pct: Optional[float] = None
    max_transaction_usd: Optional[float] = None
    max_premium_usd: Optional[float] = None
    max_limit_usd: Optional[float] = None
    max_refund_usd: Optional[float] = None
    max_discount_pct: Optional[float] = None

    model_config = {"extra": "allow"}

    def numeric_limits(self) -> Dict[str, float]:
        """Return all positive numeric irreversible limits defined on authority."""
        limits: Dict[str, float] = {}
        for key in IRREVERSIBLE_LIMIT_KEYS:
            value = getattr(self, key, None)
            if value is not None and value > 0:
                limits[key] = float(value)
        extra = getattr(self, "__pydantic_extra__", None) or {}
        for key, value in extra.items():
            if key == "irreversible_limits" and isinstance(value, dict):
                for nested_key, nested_val in value.items():
                    canon = normalize_limit_key(str(nested_key))
                    if isinstance(nested_val, (int, float)) and nested_val > 0:
                        limits.setdefault(canon, float(nested_val))
                continue
            canon = normalize_limit_key(str(key))
            if isinstance(value, (int, float)) and value > 0:
                limits.setdefault(canon, float(value))
        return limits


class ResponsibilitySpec(BaseModel):
    """Governance requirements enforced in User Space and by Post-Execution Monitors."""

    explainability: ExplainabilityLiteral = "required"
    evidence_level: EvidenceLevelLiteral = "medium"
    escalation: EscalationLiteral = "mandatory"
    escalate_on_uncertainty: float = Field(default=0.7, ge=0.0, le=1.0)
    aggregate_thresholds: Dict[str, float] = Field(default_factory=dict)


class CanonicalContract(BaseModel):
    """Canonical nested Responsibility Contract (ROA Manifesto section 3.1)."""

    agent_id: str
    version: str = "1.0.0"
    owner: str
    role: ContractRoleLiteral = "EXECUTOR"
    mission: str
    authority: AuthoritySpec
    responsibility: ResponsibilitySpec = Field(default_factory=ResponsibilitySpec)

    @field_validator("version")
    @classmethod
    def version_must_be_semver_like(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError("version must be SemVer-like (e.g. 1.0.0)")
        return value

    @classmethod
    def from_raw(cls, data: Dict[str, Any]) -> "CanonicalContract":
        """Validate after normalizing nested limits / aliases."""
        return cls.model_validate(normalize_contract_dict(data))


class InterviewAnswers(BaseModel):
    """Collected answers from CLI or Cursor interview."""

    preset: str = "generic"
    agent_id: str
    owner: str
    role: ContractRoleLiteral = "EXECUTOR"
    mission: str
    allowed_policy_types: List[str] = Field(default_factory=list)
    authorized_instruments: List[str] = Field(default_factory=list)
    irreversible_limits: Dict[str, float] = Field(
        default_factory=dict,
        description="Bootstrap hard limits keyed by authority field name",
    )
    explainability: ExplainabilityLiteral = "required"
    evidence_level: EvidenceLevelLiteral = "medium"
    escalation: EscalationLiteral = "mandatory"
    escalate_on_uncertainty: float = 0.7
    version: str = "1.0.0"

    def to_canonical(self) -> CanonicalContract:
        """Build CanonicalContract from interview answers."""
        authority_data: Dict[str, Any] = {
            "authorized_instruments": self.authorized_instruments,
            "allowed_policy_types": self.allowed_policy_types,
        }
        authority_data.update(self.irreversible_limits)
        return CanonicalContract(
            agent_id=self.agent_id,
            version=self.version,
            owner=self.owner,
            role=self.role,
            mission=self.mission,
            authority=AuthoritySpec(**authority_data),
            responsibility=ResponsibilitySpec(
                explainability=self.explainability,
                evidence_level=self.evidence_level,
                escalation=self.escalation,
                escalate_on_uncertainty=self.escalate_on_uncertainty,
            ),
        )
