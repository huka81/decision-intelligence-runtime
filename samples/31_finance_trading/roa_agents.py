"""
ROA agents with LLM-based Explain and Policy (ROA Manifesto §4).

Base class implements Explain(LLM) → Policy(LLM) → Self-Check → Proposal.
Subclasses: Instrument (observation scope), Position (observation + entry), NewsScorer (news payload).
Contract and mission come from config.
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from dir_runtime import (
    AgentState,
    EscalationRequest,
    ExplainResult,
    Policy,
    PolicyProposal,
    ResponsibilityContract,
    SelfCheckResult,
    new_dfid,
)
from dir_runtime.logging_utils import log_with_dfid
from dir_runtime.models import DecisionRecord

try:
    from .llm_client import LLMClient
except ImportError:
    from llm_client import LLMClient

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# LLM response parsing (simple regex / line-based)
# -----------------------------------------------------------------------------


def _truncate(s: str, max_len: int = 120) -> str:
    """Truncate string for logging."""
    s = s.replace("\n", " ")
    return s[:max_len] + "..." if len(s) > max_len else s


def _parse_explain_response(text: str, dfid: str, agent_id: str) -> ExplainResult:
    """Parse LLM Explain output into ExplainResult."""
    narrative = text
    signals: List[str] = []
    risks: List[str] = []
    opportunities: List[str] = []

    # Try structured blocks (SIGNALS: ... RISKS: ... OPPORTUNITIES: ...)
    for block, key in [
        (r"SIGNALS?:\s*(.+?)(?=RISKS?:|OPPORTUNITIES?:|$)", "signals"),
        (r"RISKS?:\s*(.+?)(?=SIGNALS?:|OPPORTUNITIES?:|$)", "risks"),
        (r"OPPORTUNITIES?:\s*(.+?)(?=SIGNALS?:|RISKS?:|$)", "opportunities"),
    ]:
        m = re.search(block, text, re.DOTALL | re.IGNORECASE)
        if m:
            part = m.group(1).strip()
            if key == "signals":
                signals = [s.strip() for s in re.split(r"[,;]", part) if s.strip()]
            elif key == "risks":
                risks = [s.strip() for s in re.split(r"[,;]", part) if s.strip()]
            else:
                opportunities = [s.strip() for s in re.split(r"[,;]", part) if s.strip()]

    # Narrative: take first sentence or first line
    if "Narrative:" in text:
        n = re.search(r"Narrative:\s*(.+?)(?=SIGNALS?:|RISKS?:|OPPORTUNITIES?:|$)", text, re.DOTALL | re.IGNORECASE)
        if n:
            narrative = n.group(1).strip()
    if not narrative:
        narrative = text[:300] if len(text) > 300 else text

    result = ExplainResult(
        dfid=dfid,
        agent_id=agent_id,
        narrative=narrative,
        identified_signals=signals or ["context_observed"],
        risks=risks or [],
        opportunities=opportunities or [],
        context_summary={},
    )
    log_with_dfid(
        logger, dfid, logging.INFO,
        "Explain parsed from LLM: narrative=%s | signals=%s | risks=%s | opportunities=%s",
        _truncate(result.narrative),
        result.identified_signals,
        result.risks,
        result.opportunities,
    )
    return result


def _parse_policy_response(text: str, dfid: str, agent_id: str, allowed_types: List[str]) -> Policy:
    """Parse LLM Policy output into Policy. Falls back to HOLD if parse fails."""
    action = "HOLD"
    justification = "No structured response from LLM."
    confidence = 0.5

    m = re.search(r"ACTION:\s*(\w+)", text, re.IGNORECASE)
    if m:
        raw = m.group(1).strip().upper()
        if raw in (t.upper() for t in allowed_types):
            action = raw
        elif allowed_types:
            action = allowed_types[0]

    j = re.search(r"JUSTIFICATION:\s*(.+?)(?=CONFIDENCE:|$)", text, re.DOTALL | re.IGNORECASE)
    if j:
        justification = j.group(1).strip()[:500]

    c = re.search(r"CONFIDENCE:\s*([\d.]+)", text, re.IGNORECASE)
    if c:
        try:
            confidence = float(c.group(1))
            confidence = max(0.0, min(1.0, confidence))
        except ValueError:
            pass

    result = Policy(
        dfid=dfid,
        agent_id=agent_id,
        proposed_action=action,
        justification=justification,
        confidence=confidence,
        assumptions=[],
        expected_outcomes=[],
        explain_ref=None,
    )
    log_with_dfid(
        logger, dfid, logging.INFO,
        "Policy parsed from LLM: action=%s | confidence=%.2f | justification=%s",
        result.proposed_action,
        result.confidence,
        _truncate(result.justification),
    )
    return result


# -----------------------------------------------------------------------------
# Base ROA agent with LLM (Explain → Policy → Self-Check → Proposal)
# -----------------------------------------------------------------------------


class ROAAgentLLMBase:
    """
    ROA agent that uses an LLM for Explain and Policy (Manifesto §4).
    Self-Check and emit_proposal are deterministic. Contract and mission from config.
    """

    def __init__(self, contract: ResponsibilityContract, llm: LLMClient):
        self.contract = contract
        self.llm = llm
        self.state = AgentState(agent_id=contract.agent_id)

    @property
    def agent_id(self) -> str:
        return self.contract.agent_id

    @property
    def scope(self) -> Optional[str]:
        return None

    def explain(self, dfid: str, context: Dict[str, Any]) -> ExplainResult:
        """§4.1: LLM interprets context through mission."""
        system = (
            f"Mission: {self.contract.mission}\n"
            f"Authority: you may only reason about these instruments: {self.contract.authorized_instruments or 'any'}.\n"
            "Output format: Narrative: <short summary>. SIGNALS: <comma-separated>. RISKS: <comma-separated>. OPPORTUNITIES: <comma-separated>."
        )
        user = "Current context:\n" + "\n".join(f"  {k}: {v}" for k, v in context.items())
        log_with_dfid(logger, dfid, logging.DEBUG, "[%s] Calling LLM for Explain (context keys: %s)", self.agent_id, list(context.keys()))
        response = self.llm.generate(user, system=system)
        return _parse_explain_response(response, dfid, self.agent_id)

    def formulate_policy(self, dfid: str, explain_result: ExplainResult) -> Policy:
        """§4.2: LLM proposes one action from allowed_policy_types."""
        allowed = self.contract.allowed_policy_types or ["HOLD"]
        system = (
            f"Mission: {self.contract.mission}\n"
            f"You must choose exactly one action from this list: {', '.join(allowed)}.\n"
            "Output format (one per line): ACTION: <action>\\nJUSTIFICATION: <short reason>\\nCONFIDENCE: <0.0-1.0>"
        )
        user = (
            f"Interpretation: {explain_result.narrative}\n"
            f"Signals: {explain_result.identified_signals}\n"
            f"Risks: {explain_result.risks}\n"
            f"Opportunities: {explain_result.opportunities}\n"
            "Choose one action and output ACTION, JUSTIFICATION, CONFIDENCE."
        )
        log_with_dfid(logger, dfid, logging.DEBUG, "[%s] Calling LLM for Policy (allowed: %s)", self.agent_id, allowed)
        response = self.llm.generate(user, system=system)
        return _parse_policy_response(response, dfid, self.agent_id, allowed)

    def self_check(self, policy: Policy) -> SelfCheckResult:
        """§4.3: Deterministic boundary check."""
        if policy.confidence < self.contract.escalate_on_uncertainty:
            return SelfCheckResult(
                passed=False,
                reason=f"Confidence {policy.confidence:.2f} below threshold {self.contract.escalate_on_uncertainty}",
                should_escalate=True,
                escalation_trigger="uncertainty_threshold",
            )
        action_type = policy.proposed_action.split(":")[0] if ":" in policy.proposed_action else policy.proposed_action
        if self.contract.allowed_policy_types and action_type not in self.contract.allowed_policy_types:
            return SelfCheckResult(
                passed=False,
                reason=f"Action '{action_type}' not in {self.contract.allowed_policy_types}",
                should_escalate=True,
                escalation_trigger="authority_breach",
            )
        return SelfCheckResult(passed=True)

    def emit_proposal(self, dfid: str, policy: Policy, context: Optional[Dict[str, Any]] = None) -> PolicyProposal:
        """§4.4: Build PolicyProposal; subclasses can add params via _enrich_params."""
        params: Dict[str, Any] = {
            "assumptions": policy.assumptions,
            "expected_outcomes": policy.expected_outcomes,
        }
        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy.proposed_action,
            params=params,
            confidence=policy.confidence,
            justification=policy.justification,
            explain_ref=policy.explain_ref,
        )
        self._enrich_proposal_params(proposal, context or {})
        return proposal

    def _enrich_proposal_params(self, proposal: PolicyProposal, context: Dict[str, Any]) -> None:
        """Override in subclasses to add instrument, price, position_id, pnl_pct, etc."""
        pass

    def create_escalation(self, dfid: str, policy: Policy, trigger: str) -> EscalationRequest:
        """§5.3: Escalation when limits reached."""
        return EscalationRequest(
            dfid=dfid,
            from_agent_id=self.agent_id,
            to_agent_id=self.contract.parent_agent_id,
            trigger=trigger,
            context={"mission": self.contract.mission},
            original_policy=policy,
            severity="MEDIUM" if trigger == "uncertainty_threshold" else "HIGH",
        )

    def record_decision(
        self,
        dfid: str,
        explain_result: ExplainResult,
        policy: Policy,
        outcome: str,
        reason: Optional[str] = None,
    ) -> None:
        """§3.4: Append to decision trajectory."""
        record = DecisionRecord(
            dfid=dfid,
            explain_summary=explain_result.narrative[:100],
            policy_action=policy.proposed_action,
            policy_confidence=policy.confidence,
            outcome=outcome,
            outcome_reason=reason,
        )
        self.state.decision_trajectory.append(record)
        self.state.last_active = datetime.now(timezone.utc)

    def run_decision_cycle(
        self, dfid: str, context: Dict[str, Any]
    ) -> Union[PolicyProposal, EscalationRequest]:
        """Explain → Policy → Self-Check → Proposal or Escalation."""
        log_with_dfid(logger, dfid, logging.INFO, "[%s] Starting decision cycle", self.agent_id)
        explain_result = self.explain(dfid, context)
        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Explain: %d signals, %d risks, %d opportunities",
            self.agent_id,
            len(explain_result.identified_signals),
            len(explain_result.risks),
            len(explain_result.opportunities),
        )
        policy = self.formulate_policy(dfid, explain_result)
        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Policy: action='%s' confidence=%.2f",
            self.agent_id, policy.proposed_action, policy.confidence,
        )
        check_result = self.self_check(policy)
        if not check_result.passed:
            log_with_dfid(
                logger, dfid, logging.WARNING,
                "[%s] Self-check FAILED: %s (escalate=%s)",
                self.agent_id, check_result.reason, check_result.should_escalate,
            )
            self.record_decision(dfid, explain_result, policy, "ESCALATED", check_result.reason)
            return self.create_escalation(dfid, policy, check_result.escalation_trigger or "unknown")
        proposal = self.emit_proposal(dfid, policy, context)
        self.record_decision(dfid, explain_result, policy, "ACCEPTED")
        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Proposal emitted: kind=%s confidence=%.2f",
            self.agent_id, proposal.policy_kind, proposal.confidence,
        )
        return proposal


# -----------------------------------------------------------------------------
# Instrument agent (observation scope)
# -----------------------------------------------------------------------------


class ROAInstrumentAgent(ROAAgentLLMBase):
    """Instrument-level ROA agent: reacts to market observations, scope = instrument."""

    def __init__(self, contract: ResponsibilityContract, llm: LLMClient, instrument: str):
        super().__init__(contract, llm)
        self.instrument = instrument

    @property
    def scope(self) -> Optional[str]:
        return self.instrument

    def _enrich_proposal_params(self, proposal: PolicyProposal, context: Dict[str, Any]) -> None:
        proposal.params["instrument"] = self.instrument
        if "price" in context:
            proposal.params["price"] = context["price"]
        if "trend" in context:
            proposal.params["trend"] = context["trend"]

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        dfid = payload.get("dfid", new_dfid())
        context = {
            "instrument": payload.get("instrument", self.instrument),
            "price": payload.get("price"),
            "trend": payload.get("trend", "neutral"),
            "volatility": payload.get("volatility"),
            "dfid": dfid,
        }
        result = self.run_decision_cycle(dfid, context)
        if isinstance(result, PolicyProposal):
            return result
        return None

    def on_news(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        return None


# -----------------------------------------------------------------------------
# Position agent (observation + entry_price)
# -----------------------------------------------------------------------------


class ROAPositionAgent(ROAAgentLLMBase):
    """Position-level ROA agent: manages one position, scope = instrument."""

    def __init__(
        self,
        contract: ResponsibilityContract,
        llm: LLMClient,
        position_id: str,
        instrument: str,
        entry_price: float,
    ):
        super().__init__(contract, llm)
        self.position_id = position_id
        self.instrument = instrument
        self.entry_price = entry_price

    @property
    def scope(self) -> Optional[str]:
        return self.instrument

    def _enrich_proposal_params(self, proposal: PolicyProposal, context: Dict[str, Any]) -> None:
        price = context.get("price", self.entry_price)
        pnl_pct = (price - self.entry_price) / self.entry_price if self.entry_price else 0.0
        proposal.params["position_id"] = self.position_id
        proposal.params["instrument"] = self.instrument
        proposal.params["entry_price"] = self.entry_price
        proposal.params["price"] = price
        proposal.params["pnl_pct"] = pnl_pct

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        dfid = payload.get("dfid", new_dfid())
        price = payload.get("price", self.entry_price)
        pnl_pct = (price - self.entry_price) / self.entry_price if self.entry_price else 0.0
        context = {
            "instrument": payload.get("instrument", self.instrument),
            "price": price,
            "trend": payload.get("trend", "neutral"),
            "volatility": payload.get("volatility"),
            "entry_price": self.entry_price,
            "pnl_pct": pnl_pct,
            "position_id": self.position_id,
            "dfid": dfid,
        }
        result = self.run_decision_cycle(dfid, context)
        if isinstance(result, PolicyProposal):
            return result
        return None

    def on_news(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        return None


# -----------------------------------------------------------------------------
# News scorer agent (news payload)
# -----------------------------------------------------------------------------


class ROANewsScorerAgent(ROAAgentLLMBase):
    """Scores news; emits NEWS_QUALIFIED when score above threshold."""

    def __init__(self, contract: ResponsibilityContract, llm: LLMClient, score_threshold: float = 0.6):
        super().__init__(contract, llm)
        self.score_threshold = score_threshold

    @property
    def scope(self) -> Optional[str]:
        return None

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        return None

    def on_news(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        raw_score = payload.get("raw_score", 0.0)
        if raw_score < self.score_threshold:
            return None
        dfid = payload.get("dfid", new_dfid())
        context = {
            "headline": payload.get("headline", ""),
            "raw_score": raw_score,
            "news_id": payload.get("news_id"),
            "dfid": dfid,
        }
        result = self.run_decision_cycle(dfid, context)
        if isinstance(result, PolicyProposal):
            return result
        return None
