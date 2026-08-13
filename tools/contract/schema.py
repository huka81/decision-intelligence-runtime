"""Canonical Manifesto-aligned Responsibility Contract schema."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

import re

from pydantic import BaseModel, Field, field_validator, model_validator

ContractRoleLiteral = Literal["STRATEGIST", "EXECUTOR", "MONITOR", "INTERFACE"]
ExplainabilityLiteral = Literal["required", "optional"]
EvidenceLevelLiteral = Literal["high", "medium", "low"]
EscalationLiteral = Literal["mandatory", "conditional", "disabled"]
AggregateOperatorLiteral = Literal["gt", "ge", "lt", "le", "eq"]
AggregateResponseLiteral = Literal["SUSPENDED", "ESCALATION_ONLY", "DEGRADED"]

# Temporal windows for aggregate policies (e.g. 24h, 7d, 30d).
_TEMPORAL_WINDOW_RE = re.compile(r"^\d+[hdwm]$", re.IGNORECASE)
_NON_TEMPORAL_WINDOW_TOKENS = frozenset(
    {"1t", "txn", "transaction", "per_tx", "single", "per_transaction"}
)

PLACEHOLDER_AGENT_IDS = frozenset({"draft_agent"})
PLACEHOLDER_OWNERS = frozenset({"owner@example.com", ""})

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
}


def normalize_limit_key(key: str) -> str:
    """Map alias limit names to canonical IRREVERSIBLE_LIMIT_KEYS."""
    return LIMIT_KEY_ALIASES.get(key, key)


def _limit_unit(key: str) -> str:
    if key.endswith("_usd"):
        return "USD"
    if key.endswith("_eur"):
        return "EUR"
    if key.endswith("_pct") or "percentage" in key:
        return "percent"
    return "unitless"


def _normalize_aggregate_policy_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Map legacy aggregate policy keys before schema validation."""
    out = dict(entry)
    if "on_breach" in out and "response" not in out:
        out["response"] = out.pop("on_breach")
    response = out.get("response")
    if isinstance(response, str):
        upper = response.strip().upper()
        if upper == "SUSPEND":
            out["response"] = "SUSPENDED"
        elif upper == "ESCALATE":
            out["response"] = "ESCALATION_ONLY"
    return out


def _normalize_aggregate_policies(value: Any) -> List[Dict[str, Any]]:
    """
    Normalize aggregate policy list entries for schema validation.

    Plain prose or single-transaction windows are not coerced into valid policies;
    they fail AggregatePolicy validation instead.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [{"statement": value}]
    if isinstance(value, dict):
        items: List[Dict[str, Any]] = []
        for key, entry in value.items():
            if isinstance(entry, dict):
                items.append(_normalize_aggregate_policy_entry({"policy_id": key, **entry}))
            elif isinstance(entry, (int, float)):
                items.append(
                    _normalize_aggregate_policy_entry(
                        {"policy_id": key, "threshold": float(entry)}
                    )
                )
            else:
                items.append({"policy_id": key, "statement": str(entry)})
        return items
    if not isinstance(value, list):
        return [{"statement": str(value)}]

    normalized: List[Dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            normalized.append(_normalize_aggregate_policy_entry(dict(entry)))
        elif entry is not None:
            normalized.append({"statement": str(entry)})
    return normalized


def is_temporal_aggregate_window(window: str) -> bool:
    """Return True when window is a rolling time window (not single-transaction)."""
    token = window.strip().lower()
    if token in _NON_TEMPORAL_WINDOW_TOKENS:
        return False
    return bool(_TEMPORAL_WINDOW_RE.match(token))


def normalize_contract_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy and LLM-authored input to the canonical envelope."""
    out = dict(data)

    metadata = dict(out.get("metadata") or {})
    subject = dict(out.get("subject") or {})
    metadata.setdefault("contract_id", out.get("agent_id") or subject.get("agent_id"))
    metadata.setdefault("version", out.get("version", "1.0.0"))
    if "owner" not in metadata and "owner" in out:
        metadata["owner"] = out["owner"]
    subject.setdefault("agent_id", out.get("agent_id"))
    subject.setdefault("role", out.get("role", "EXECUTOR"))
    if "parent_agent_id" not in subject and out.get("parent_agent_id") is not None:
        subject["parent_agent_id"] = out["parent_agent_id"]

    mission = out.get("mission") or {}
    if isinstance(mission, str):
        mission = {"statement": mission}

    authority = dict(out.get("authority") or {})
    resource_scope = dict(authority.get("resource_scope") or {})
    if "authorized_instruments" in authority:
        resource_scope.setdefault("instruments", authority.pop("authorized_instruments"))

    raw_limits = dict(authority.get("limits") or {})
    nested_limits = authority.pop("irreversible_limits", None)
    if isinstance(nested_limits, dict):
        raw_limits.update(nested_limits)

    for key in list(authority):
        canonical_key = normalize_limit_key(str(key))
        if canonical_key in IRREVERSIBLE_LIMIT_KEYS:
            raw_limits.setdefault(canonical_key, authority.pop(key))

    limits: Dict[str, Any] = {}
    for key, value in raw_limits.items():
        canonical_key = normalize_limit_key(str(key))
        if isinstance(value, (int, float)):
            limits[canonical_key] = {
                "value": float(value),
                "unit": _limit_unit(canonical_key),
            }
        else:
            limits[canonical_key] = value
    authority["resource_scope"] = resource_scope
    authority["limits"] = limits

    responsibility = dict(out.get("responsibility") or {})
    evidence = dict(responsibility.get("evidence") or {})
    if "evidence_level" in responsibility:
        evidence.setdefault("level", responsibility.pop("evidence_level"))
    escalation = responsibility.get("escalation") or {}
    if isinstance(escalation, str):
        escalation = {"mode": escalation}
    else:
        escalation = dict(escalation)
    if "escalate_on_uncertainty" in responsibility:
        escalation.setdefault(
            "confidence_below", responsibility.pop("escalate_on_uncertainty")
        )
    responsibility["evidence"] = evidence
    responsibility["escalation"] = escalation

    governance = dict(out.get("governance") or {})
    if "aggregate_thresholds" in responsibility:
        governance.setdefault(
            "aggregate_thresholds", responsibility.pop("aggregate_thresholds")
        )
    if "aggregate_monitors" in out and "aggregate_thresholds" not in governance:
        governance["aggregate_thresholds"] = out["aggregate_monitors"]
    if "aggregate_policies" in governance:
        governance["aggregate_policies"] = _normalize_aggregate_policies(
            governance["aggregate_policies"]
        )

    canonical = {
        "api_version": out.get("api_version", "roa.dir/v1"),
        "kind": out.get("kind", "ResponsibilityContract"),
        "metadata": metadata,
        "subject": subject,
        "mission": mission,
        "authority": authority,
        "execution_conditions": dict(out.get("execution_conditions") or {}),
        "responsibility": responsibility,
        "governance": governance,
    }
    return canonical


class ContractMetadata(BaseModel):
    contract_id: str
    version: str = "1.0.0"
    owner: str = ""
    source_refs: List[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @field_validator("version")
    @classmethod
    def version_must_be_semver_like(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError("version must be SemVer-like (e.g. 1.0.0)")
        return value


class ContractSubject(BaseModel):
    agent_id: str
    role: ContractRoleLiteral = "EXECUTOR"
    parent_agent_id: Optional[str] = None

    model_config = {"extra": "allow"}


class MissionSpec(BaseModel):
    statement: str

    model_config = {"extra": "allow"}


class LimitSpec(BaseModel):
    value: float
    unit: str

    model_config = {"extra": "allow"}


class AuthoritySpec(BaseModel):
    """Deterministic boundaries enforced by DIM in Kernel Space."""

    allowed_policy_types: List[str] = Field(default_factory=list)
    resource_scope: Dict[str, List[str]] = Field(default_factory=dict)
    limits: Dict[str, LimitSpec] = Field(default_factory=dict)
    exclusions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    def numeric_limits(self) -> Dict[str, float]:
        """Return all positive numeric irreversible limits defined on authority."""
        return {
            key: float(limit.value)
            for key, limit in self.limits.items()
            if limit.value > 0
        }

    @property
    def authorized_instruments(self) -> List[str]:
        return self.resource_scope.get("instruments", [])


class EvidenceSpec(BaseModel):
    level: EvidenceLevelLiteral = "medium"
    required_attestations: List[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class EscalationSpec(BaseModel):
    mode: EscalationLiteral = "mandatory"
    confidence_below: float = Field(default=0.7, ge=0.0, le=1.0)
    route_to: Optional[str] = None

    model_config = {"extra": "allow"}


class ResponsibilitySpec(BaseModel):
    """Governance requirements enforced in User Space and by Post-Execution Monitors."""

    explainability: ExplainabilityLiteral = "required"
    evidence: EvidenceSpec = Field(default_factory=EvidenceSpec)
    escalation: EscalationSpec = Field(default_factory=EscalationSpec)

    model_config = {"extra": "allow"}


class ExecutionConditionsSpec(BaseModel):
    model_config = {"extra": "allow"}


class AggregatePolicy(BaseModel):
    """Post-execution aggregate monitor rule (rolling window, MONITOR scope)."""

    policy_id: str
    metric: str
    window: str
    operator: AggregateOperatorLiteral
    threshold: float
    unit: str
    response: AggregateResponseLiteral
    statement: str = ""

    model_config = {"extra": "forbid"}

    @field_validator("window")
    @classmethod
    def window_must_be_temporal(cls, value: str) -> str:
        token = value.strip()
        lower = token.lower()
        if lower in _NON_TEMPORAL_WINDOW_TOKENS:
            raise ValueError(
                f"aggregate window '{value}' is single-transaction; "
                "use authority.limits instead"
            )
        if not _TEMPORAL_WINDOW_RE.match(token):
            raise ValueError(
                f"aggregate window '{value}' must be temporal (e.g. 24h, 7d, 30d)"
            )
        return token


class GovernanceSpec(BaseModel):
    aggregate_policies: List[AggregatePolicy] = Field(default_factory=list)
    aggregate_thresholds: Optional[Dict[str, float]] = None

    model_config = {"extra": "allow"}


class CanonicalContract(BaseModel):
    """Canonical nested Responsibility Contract (ROA Manifesto section 3.1)."""

    api_version: Literal["roa.dir/v1"] = "roa.dir/v1"
    kind: Literal["ResponsibilityContract"] = "ResponsibilityContract"
    metadata: ContractMetadata
    subject: ContractSubject
    mission: MissionSpec
    authority: AuthoritySpec
    execution_conditions: ExecutionConditionsSpec = Field(
        default_factory=ExecutionConditionsSpec
    )
    responsibility: ResponsibilitySpec = Field(default_factory=ResponsibilitySpec)
    governance: GovernanceSpec = Field(default_factory=GovernanceSpec)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return normalize_contract_dict(value)
        return value

    @property
    def agent_id(self) -> str:
        return self.subject.agent_id

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def owner(self) -> str:
        return self.metadata.owner

    @property
    def role(self) -> ContractRoleLiteral:
        return self.subject.role

    @property
    def mission_statement(self) -> str:
        return self.mission.statement

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
    limit_units: Dict[str, str] = Field(
        default_factory=dict,
        description="Units for irreversible_limits; inferred when omitted",
    )
    explainability: ExplainabilityLiteral = "required"
    evidence_level: EvidenceLevelLiteral = "medium"
    escalation: EscalationLiteral = "mandatory"
    escalate_on_uncertainty: float = 0.7
    version: str = "1.0.0"

    def to_canonical(self) -> CanonicalContract:
        """Build CanonicalContract from interview answers."""
        authority_data: Dict[str, Any] = {
            "resource_scope": {"instruments": self.authorized_instruments},
            "allowed_policy_types": self.allowed_policy_types,
            "limits": {
                key: {
                    "value": value,
                    "unit": self.limit_units.get(key, _limit_unit(key)),
                }
                for key, value in self.irreversible_limits.items()
            },
        }
        return CanonicalContract(
            metadata={
                "contract_id": self.agent_id,
                "version": self.version,
                "owner": self.owner,
            },
            subject={"agent_id": self.agent_id, "role": self.role},
            mission={"statement": self.mission},
            authority=AuthoritySpec(**authority_data),
            responsibility=ResponsibilitySpec(
                explainability=self.explainability,
                evidence={"level": self.evidence_level},
                escalation={
                    "mode": self.escalation,
                    "confidence_below": self.escalate_on_uncertainty,
                },
            ),
        )
