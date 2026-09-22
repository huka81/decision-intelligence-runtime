"""
Domain schemas for the Digital Underwriter (Topology C / DL+PCI).
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


__all__ = [
    "UnderwritingContract",
    "ClientApplication",
    "UnderwritingProposal",
]


class UnderwritingContract(BaseModel):
    """Canonical insurance contract consumed at handshake."""

    api_version: str = "roa.dir/v1"
    kind: str = "ResponsibilityContract"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    subject: Dict[str, Any] = Field(default_factory=dict)
    mission: str = "Underwrite insurance policies for compliant businesses."
    authority: Dict[str, Any] = Field(default_factory=dict)
    responsibility: Dict[str, Any] = Field(default_factory=dict)


class ClientApplication(BaseModel):
    """Client application state held in the Context Store."""

    industry: str = Field(description="Industry classification from coarse ingest")
    source_file: Optional[str] = Field(
        default=None,
        description="Source email fixture filename when ingested from markdown",
    )
    mail_subject: Optional[str] = Field(default=None, description="Email subject line")
    mail_body_sha256: Optional[str] = Field(
        default=None,
        description="SHA256 of raw email body for audit (LG-4: avoid storing full PII)",
    )


class UnderwritingProposal(BaseModel):
    """Agent User Space claim; serialized as JSON in PCI ``intent_payload``."""

    total_insured_value: float = Field(
        description="Proposed Total Insured Value (TiV) in USD",
    )
    territory: str = Field(
        description="Geographic exposures named in the submission",
    )
    justification: str = Field(
        default="",
        description="Agent textual reasoning for proposed terms",
    )
