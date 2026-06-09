"""ROA credit-limit agent: Explain → Policy → Self-Check → Proposal (User Space)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from dir_core import PolicyProposal
from dir_core.utils.logging_utils import log_with_dfid

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


@dataclass
class CreditAgentContext:
    dfid: str
    agent_id: str
    chat_transcript: str
    mission: str
    allowed_policy_types: list[str]
    escalate_on_uncertainty: float


class CreditLimitAgent:
    """Minimal ROA agent for credit-limit decisions."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def explain(self, ctx: CreditAgentContext) -> str:
        prompt = (
            f"Mission: {ctx.mission}\n"
            f"Chat transcript:\n{ctx.chat_transcript}\n"
            "Explain the customer request in one short narrative."
        )
        return self._llm.generate(prompt, system=ctx.mission)

    def formulate_policy(
        self, ctx: CreditAgentContext, explain_text: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        prompt = (
            f"Mission: {ctx.mission}\n"
            f"Explain result:\n{explain_text}\n"
            f"Chat:\n{ctx.chat_transcript}\n"
            "Return JSON with policy_kind, params "
            "(customer_id, declared_income_pln, requested_limit_pln, current_limit_pln), "
            "confidence, justification."
        )
        raw = self._llm.generate(prompt, system=ctx.mission)
        parsed = parse_llm_json(raw)
        if not parsed:
            return None, "PARSE_FAILED"
        return parsed, raw

    def self_check(
        self,
        policy: Dict[str, Any],
        ctx: CreditAgentContext,
    ) -> Tuple[bool, str]:
        kind = policy.get("policy_kind")
        if kind not in ctx.allowed_policy_types:
            return False, f"policy_kind {kind} not in contract"
        try:
            conf = float(policy.get("confidence", 0.0))
        except (TypeError, ValueError):
            return False, "invalid confidence"
        if conf < ctx.escalate_on_uncertainty:
            return False, f"confidence {conf} below threshold"
        return True, "OK"

    def run_roa_cycle(
        self, ctx: CreditAgentContext
    ) -> Tuple[Optional[PolicyProposal], str]:
        log_with_dfid(
            logger,
            ctx.dfid,
            logging.INFO,
            "[%s] ROA cycle started",
            ctx.agent_id,
        )
        explain_text = self.explain(ctx)
        policy, _raw = self.formulate_policy(ctx, explain_text)
        if policy is None:
            return None, "PARSE_FAILED"

        ok, reason = self.self_check(policy, ctx)
        if not ok:
            log_with_dfid(
                logger,
                ctx.dfid,
                logging.WARNING,
                "[%s] Self-check failed: %s",
                ctx.agent_id,
                reason,
            )
            return None, reason

        proposal = PolicyProposal(
            dfid=ctx.dfid,
            agent_id=ctx.agent_id,
            policy_kind=str(policy.get("policy_kind", "HOLD")),
            params=dict(policy.get("params", {})),
            confidence=float(policy.get("confidence", 0.0)),
            justification=str(policy.get("justification", "")),
        )
        return proposal, "OK"
