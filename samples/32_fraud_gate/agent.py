"""
FraudGuardAgent - SDS Agent for Real-Time Fraud Gate.

Uses a "Straightjacket Grammar" (FraudDecisionSchema). The LLM can ONLY
generate JSON matching the schema. In production this would use
outlines.generate.json(model, schema) or guidance for constrained decoding.

This implementation mocks the constrained inference with deterministic logic.
"""

import logging
from typing import Optional

from dir import new_dfid

try:
    from .risk_cache import RiskCache
    from .schemas import DecisionAtom, FraudDecisionSchema, TransactionContext
except ImportError:
    from risk_cache import RiskCache
    from schemas import DecisionAtom, FraudDecisionSchema, TransactionContext

logger = logging.getLogger(__name__)


def _mock_constrained_inference(
    ctx: TransactionContext,
    snapshot_id: str,
    snapshot_user_status: Optional[str],
) -> dict:
    """
    Mock for outlines.generate.json(model, FraudDecisionSchema)(prompt).

    In production, the grammar physically prevents invalid output:
        grammar = build_pydantic_grammar(FraudDecisionSchema)
        raw = generate.json(model, grammar)(prompt=...)
    """
    # Deterministic decision logic based on transaction context
    if ctx.amount > 5_000 and ctx.geo_country.lower() == "nigeria":
        return {
            "action": "BLOCK",
            "reason_code": "HIGH_RISK_GEO_AMOUNT",
            "risk_score": 0.99,
        }
    if ctx.amount < 1000 and ctx.device_id.startswith("dev_known_") and ctx.velocity_24h < 10:
        return {
            "action": "ALLOW",
            "reason_code": "LOW_RISK_LEGIT",
            "risk_score": 0.1,
        }
    # Drift-attack tx: agent sees snapshot where user is clean -> ALLOW
    # (The agent does NOT see the future state change)
    if snapshot_user_status == "clean" and ctx.amount < 1000:
        return {
            "action": "ALLOW",
            "reason_code": "LOW_RISK_SNAPSHOT",
            "risk_score": 0.15,
        }
    # Default: challenge
    return {
        "action": "CHALLENGE",
        "reason_code": "UNCERTAIN",
        "risk_score": 0.5,
    }


class FraudGuardAgent:
    """
    SDS Agent: produces syntactically valid DecisionAtom constrained by grammar.

    Input: TransactionContext + snapshot
    Output: DecisionAtom (signed, schema-perfect decision)
    """

    def __init__(self, agent_id: str, risk_cache: RiskCache) -> None:
        self.agent_id = agent_id
        self.risk_cache = risk_cache

    def decide(
        self,
        ctx: TransactionContext,
        dfid: str,
        snapshot_id: str,
    ) -> DecisionAtom:
        """
        Produce a DecisionAtom from transaction context.

        The grammar (FraudDecisionSchema) ensures output is always valid.
        Snapshot state is read at call time - agent reasons over this frozen view.
        """
        # Snapshot state at T=0 (what the agent "sees")
        snapshot_entry = self.risk_cache.get_snapshot(ctx.user_id)
        snapshot_status = snapshot_entry["status"] if snapshot_entry else None

        # Mock constrained inference - in prod: generate.json(model, FraudDecisionSchema)
        raw_decision = _mock_constrained_inference(ctx, snapshot_id, snapshot_status)

        atom = DecisionAtom(
            action=raw_decision["action"],
            reason_code=raw_decision["reason_code"],
            risk_score=raw_decision["risk_score"],
            snapshot_id=snapshot_id,
            dfid=dfid,
            user_id=ctx.user_id,
            amount=ctx.amount,
        )
        return atom
