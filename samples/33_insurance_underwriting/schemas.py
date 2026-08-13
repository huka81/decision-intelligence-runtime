"""
Domain schemas for the Digital Underwriter (Topology C / DL+PCI).

Pydantic models for insurance underwriting. ProofCarryingIntent lives in dir_core.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dir_core.models import ProofCarryingIntent


@dataclass
class EmailSubmissionExtraction:
    """Structured facts extracted from unstructured broker email (User Space / LLM)."""

    broker_requested_tiv_usd: float
    stated_territories: str


__all__ = [
    "UnderwritingContract",
    "ClientApplication",
    "PolicyProposal",
    "ProofCarryingIntent",
    "EmailSubmissionExtraction",
]


class UnderwritingContract(BaseModel):
    """Canonical insurance contract consumed directly by the sample Kernel."""

    api_version: str = "roa.dir/v1"
    kind: str = "ResponsibilityContract"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    subject: Dict[str, Any] = Field(default_factory=dict)
    mission: str = "Underwrite insurance policies for compliant businesses."
    authority: Dict[str, Any] = Field(default_factory=dict)
    responsibility: Dict[str, Any] = Field(default_factory=dict)

    @property
    def agent_id(self) -> str:
        return str(self.subject.get("agent_id", "underwriter_agent"))

    @property
    def max_tiv(self) -> float:
        limits = self.authority.get("limits") or {}
        value = limits.get("max_tiv", 2_000_000)
        return float(value.get("value", value) if isinstance(value, dict) else value)

    @property
    def prohibited_industries(self) -> List[str]:
        exclusions = self.authority.get("exclusions") or {}
        return list(exclusions.get("prohibited_industries") or [])


class ClientApplication(BaseModel):
    """Client application state held in the Context Store."""

    business_type: str = Field(description="Type of business (e.g. Retail, Factory)")
    revenue: float = Field(description="Annual revenue in USD (or contract currency)")
    industry: str = Field(description="Industry classification")
    source_file: Optional[str] = Field(
        default=None,
        description="Source email fixture filename when ingested from markdown",
    )
    mail_subject: Optional[str] = Field(default=None, description="Email subject line")
    requested_tiv_usd: Optional[float] = Field(
        default=None,
        description=(
            "Broker-declared Total Insured Value (TiV) in USD from agent LLM extraction "
            "(email pipeline), not from fixed-layout parsing"
        ),
    )
    territory_summary: Optional[str] = Field(
        default=None,
        description="Territory / wording text for kernel scans (not parsed for execution)",
    )
    mail_body_sha256: Optional[str] = Field(
        default=None,
        description="SHA256 of raw email body for audit (LG-4: avoid storing full PII)",
    )


class PolicyProposal(BaseModel):
    """Agent User Space claim; serialized as JSON in PCI ``intent_payload``."""

    total_insured_value: float = Field(
        description="Proposed Total Insured Value (TiV) in USD",
    )
    premium: float = Field(description="Proposed annual premium in USD")
    industry: str = Field(description="Industry of the proposed policy")
    justification: str = Field(
        default="",
        description=(
            "Agent textual reasoning for proposed terms (audit / human review)"
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Self-assessed certainty 0..1; not a permission grant",
    )
