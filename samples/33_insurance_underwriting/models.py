"""
Domain models for the Digital Underwriter use case (Topology C / DL+PCI).

Pydantic models for insurance underwriting: Responsibility Contract, Client Application,
Policy Proposal. ProofCarryingIntent imported from dir.models (framework).
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from dir.models import ProofCarryingIntent

__all__ = [
    "UnderwritingContract",
    "ClientApplication",
    "PolicyProposal",
    "ProofCarryingIntent",
]


# =============================================================================
# Responsibility Contract (Underwriting Policy)
# =============================================================================


class UnderwritingContract(BaseModel):
    """
    Responsibility Contract for the Digital Underwriter.

    Defines the authoritative rules that the DIM enforces. The agent must prove
    compliance via the Evidence Hash; the DIM never trusts the agent's claims.

    Audit fields (version, created_by, created_at) provide policy provenance
    for compliance and traceability.
    """

    agent_id: str = "underwriter_agent"
    # Audit metadata
    version: str = Field(
        default="1.0.0",
        description="Policy version (SemVer)",
    )
    created_by: Optional[str] = Field(
        default=None,
        description="Who created/approved the policy (e.g. compliance@example.com)",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="When the policy was created (ISO 8601)",
    )
    mission: str = Field(
        default="Underwrite insurance policies for compliant businesses.",
        description="ROA mission (Manifesto §3.2)",
    )
    max_limit: float = Field(
        default=2_000_000,
        description="Maximum coverage limit in USD",
    )
    prohibited_industries: List[str] = Field(
        default_factory=lambda: ["Fireworks", "CryptoMining"],
        description="Industries for which no policy may be issued",
    )


# =============================================================================
# Client Application (Context)
# =============================================================================


class ClientApplication(BaseModel):
    """
    Client application state held in the Context Store.

    Represents the authoritative view of the applicant: business type,
    revenue, and industry. Used to compute Context_Hash for Evidence Hash.
    """

    business_type: str = Field(description="Type of business (e.g. Retail, Factory)")
    revenue: float = Field(description="Annual revenue in USD")
    industry: str = Field(description="Industry classification")


# =============================================================================
# Policy Proposal (Agent Output)
# =============================================================================


class PolicyProposal(BaseModel):
    """
    Structured policy proposal from the UnderwriterAgent.

    The agent's decision: coverage limit, premium, and industry. These fields
    are included in Proposal_Params for Evidence Hash computation.
    """

    coverage_limit: float = Field(description="Proposed coverage limit in USD")
    premium: float = Field(description="Proposed annual premium in USD")
    industry: str = Field(description="Industry of the proposed policy")
