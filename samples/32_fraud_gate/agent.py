"""
FraudGuardAgent - SDS Agent for Real-Time Fraud Gate.

Uses a "Straightjacket Grammar" (FraudDecisionSchema). The LLM produces
JSON matching the schema via prompt-based extraction. In production this
would use outlines.generate.json(model, schema) or guidance for constrained decoding.

This implementation calls a real LLM (Ollama/Gemma) with illustrative prompts.
"""

import json
import logging
import re
from typing import Optional

try:
    from .config_loader import FallbackRules
    from .risk_cache import RiskCache
    from .schemas import DecisionAtom, TransactionContext
except ImportError:
    from config_loader import FallbackRules
    from risk_cache import RiskCache
    from schemas import DecisionAtom, TransactionContext

logger = logging.getLogger(__name__)

def _build_prompt(ctx: TransactionContext, snapshot_status: Optional[str]) -> str:
    """Build a readable, illustrative prompt for the fraud analyst LLM."""
    return f"""Evaluate this payment transaction for fraud risk.

**Transaction:**
- User: {ctx.user_id}
- Amount: ${ctx.amount:,.2f}
- Country: {ctx.geo_country}
- Device: {ctx.device_id}
- Transactions in last 24h: {ctx.velocity_24h}

**User risk status (from snapshot):** {snapshot_status or "unknown"}

**Decision rules:**
- ALLOW: Low risk, known device, reasonable amount
- BLOCK: High risk (e.g. large amount + high-risk country, unknown device)
- CHALLENGE: Uncertain, needs additional verification

Respond with ONLY a valid JSON object, no other text. Example:
{{"action": "ALLOW", "reason_code": "LOW_RISK_LEGIT", "risk_score": 0.1}}
"""


def _build_system_prompt(mission: str = "") -> str:
    """System prompt for the fraud analyst role."""
    base = mission or "You are a fraud analyst for a payment gateway."
    return f"""{base} Evaluate each transaction and output ONLY a JSON object with:
- action: "ALLOW" | "BLOCK" | "CHALLENGE"
- reason_code: short code (e.g. LOW_RISK_LEGIT, HIGH_RISK_GEO_AMOUNT, UNCERTAIN)
- risk_score: float between 0.0 and 1.0

Respond with nothing else - no markdown, no explanation, just the JSON."""


def _parse_llm_response(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response. Handles markdown code blocks."""
    text = raw.strip()
    # Try to find JSON in ```json ... ``` or ``` ... ```
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
    # Try to find {...}
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM response not valid JSON: %s", raw[:200])
        return None


def _fallback_decision(
    ctx: TransactionContext,
    snapshot_status: Optional[str],
    rules: FallbackRules,
) -> dict:
    """Fallback when LLM returns invalid JSON - deterministic logic from config."""
    geo_lower = ctx.geo_country.lower()
    if ctx.amount > rules.block_amount_threshold and geo_lower in rules.block_high_risk_countries:
        return {"action": "BLOCK", "reason_code": "HIGH_RISK_GEO_AMOUNT", "risk_score": 0.99}
    if (
        ctx.amount < rules.allow_amount_max
        and ctx.device_id.startswith(rules.allow_device_prefix)
        and ctx.velocity_24h < rules.allow_velocity_max
    ):
        return {"action": "ALLOW", "reason_code": "LOW_RISK_LEGIT", "risk_score": 0.1}
    if snapshot_status == "clean" and ctx.amount < rules.allow_amount_max:
        return {"action": "ALLOW", "reason_code": "LOW_RISK_SNAPSHOT", "risk_score": 0.15}
    return {"action": "CHALLENGE", "reason_code": "UNCERTAIN", "risk_score": 0.5}


def _validate_and_normalize(raw: dict) -> Optional[dict]:
    """Validate and normalize LLM output to match schema."""
    action = raw.get("action")
    if isinstance(action, str):
        action = action.upper().strip()
        if action not in ("ALLOW", "BLOCK", "CHALLENGE"):
            return None
    else:
        return None

    reason_code = raw.get("reason_code")
    if not isinstance(reason_code, str):
        reason_code = str(reason_code or "UNKNOWN")

    try:
        risk_score = float(raw.get("risk_score", 0.5))
        risk_score = max(0.0, min(1.0, risk_score))
    except (TypeError, ValueError):
        risk_score = 0.5

    return {
        "action": action,
        "reason_code": reason_code,
        "risk_score": risk_score,
    }


class FraudGuardAgent:
    """
    SDS Agent: produces syntactically valid DecisionAtom constrained by grammar.

    Input: TransactionContext + snapshot
    Output: DecisionAtom (signed, schema-perfect decision)
    """

    def __init__(
        self,
        agent_id: str,
        risk_cache: RiskCache,
        llm: Optional[object] = None,
        fallback_rules: Optional[FallbackRules] = None,
        mission: str = "",
    ):
        self.agent_id = agent_id
        self.risk_cache = risk_cache
        self.llm = llm
        self.fallback_rules = fallback_rules or FallbackRules(
            block_amount_threshold=5000,
            block_high_risk_countries=["nigeria"],
            allow_amount_max=1000,
            allow_velocity_max=10,
            allow_device_prefix="dev_known_",
        )
        self.mission = mission

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
        snapshot_entry = self.risk_cache.get_snapshot(ctx.user_id)
        snapshot_status = snapshot_entry["status"] if snapshot_entry else None

        if self.llm:
            prompt = _build_prompt(ctx, snapshot_status)
            system = _build_system_prompt(self.mission)
            logger.debug(
                "[LLM REQUEST] user=%s amount=$%.2f country=%s device=%s velocity=%d",
                ctx.user_id, ctx.amount, ctx.geo_country, ctx.device_id, ctx.velocity_24h,
            )
            raw_response = self.llm.generate(prompt, system=system)
            parsed = _parse_llm_response(raw_response)
            if parsed:
                validated = _validate_and_normalize(parsed)
                if validated:
                    raw_decision = validated
                else:
                    raw_decision = _fallback_decision(ctx, snapshot_status, self.fallback_rules)
                    logger.warning("LLM output invalid, using fallback: %s", raw_decision)
            else:
                raw_decision = _fallback_decision(ctx, snapshot_status, self.fallback_rules)
                logger.warning("LLM response not parseable, using fallback: %s", raw_decision)
        else:
            raw_decision = _fallback_decision(ctx, snapshot_status, self.fallback_rules)

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
