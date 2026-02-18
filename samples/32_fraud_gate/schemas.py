"""
Pydantic schemas for Real-Time Fraud Gate (Topology B SDS).

- FraudDecisionSchema: The "Straightjacket Grammar" - the LLM can ONLY output
  JSON matching this schema (via outlines/guidance constrained decoding).
- DecisionAtom: Agent output with snapshot binding for JIT verification.
- TransactionContext: Input context for the agent.
"""

from typing import Literal

from pydantic import BaseModel, Field


class FraudDecisionSchema(BaseModel):
    """Straightjacket Grammar - constrained decoding output.

    In production, this schema is used with outlines.generate.json(model, schema)
    to physically prevent the LLM from generating invalid tokens.
    """

    action: Literal["ALLOW", "BLOCK", "CHALLENGE"]
    reason_code: str
    risk_score: float = Field(ge=0.0, le=1.0)


class TransactionContext(BaseModel):
    """Transaction context passed to the agent."""

    user_id: str
    amount: float
    geo_country: str
    device_id: str
    velocity_24h: int


class DecisionAtom(FraudDecisionSchema):
    """Signed decision with snapshot binding for JIT check.

    DIR Topologies §3.1.2: The DecisionAtom MUST include snapshot_id hash-binding
    so the JIT Validator can verify state has not drifted since the snapshot.
    """

    snapshot_id: str = Field(description="Context snapshot hash for JIT drift check")
    dfid: str = Field(description="DecisionFlow ID for correlation")
    user_id: str = Field(description="User ID for risk cache lookup")
    amount: float = Field(description="Transaction amount for hard limit check")
