#!/usr/bin/env python3
"""
01_roa_agent - Full ROA agent example demonstrating:
- Responsibility Contract with mission and authority boundaries (§3.1-3.3)
- Long-lived agents with state and memory (§3.4)
- Decision lifecycle: Explain → Policy → Self-Check → Policy Proposal (§4)
- Dynamic Agents: InstrumentAgent (class-level) → PositionAgent (instance-level) (§6)
- Escalation paths when authority limits are reached (§5.3)

Run from repo root: python samples/01_roa/run.py
Requires PYTHONPATH including workspace src/ (see .vscode/settings.json).

ROA Manifesto alignment: §3-4, §6
"""
from __future__ import annotations

import json
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from dir import (
    AgentState,
    DecisionRecord,
    EscalationRequest,
    ExplainResult,
    Policy,
    PolicyProposal,
    ResponsibilityContract,
    SelfCheckResult,
    new_dfid,
)
from dir.logging_utils import log_with_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# ROA Agent Base Class (Manifesto §3)
# =============================================================================


class ROAAgent(ABC):
    """Base class for Responsibility-Oriented Agents.
    
    Each ROA agent:
    - Has a ResponsibilityContract defining scope, authority, mission (§3.1)
    - Maintains long-lived state with decision trajectory (§3.4)
    - Follows the Explain → Policy → Self-Check → Proposal lifecycle (§4)
    - Can escalate when reaching authority limits (§5.3)
    """

    def __init__(self, contract: ResponsibilityContract):
        self.contract = contract
        self.state = AgentState(agent_id=contract.agent_id)
        self._child_agents: Dict[str, ROAAgent] = {}

    @property
    def agent_id(self) -> str:
        return self.contract.agent_id

    # -------------------------------------------------------------------------
    # Mission-Driven Reasoning (§3.2)
    # -------------------------------------------------------------------------

    def parse_mission_focus(self) -> Dict[str, float]:
        """§3.2: Extract mission-driven biases from the mission string.
        
        Mission is not just a label - it's an interpretive constraint that
        actively influences how the agent weighs signals during Explain.
        
        Returns weights for different signal categories based on mission keywords.
        """
        mission_lower = self.contract.mission.lower()
        
        # Default balanced weights
        focus = {
            "risk_weight": 1.0,      # How much to emphasize risks
            "opportunity_weight": 1.0,  # How much to emphasize opportunities
            "conservative_bias": 0.0,   # Bias toward conservative actions
        }
        
        # Mission keywords influence interpretation
        if any(kw in mission_lower for kw in ["protect", "risk", "defensive", "preserve", "capital"]):
            focus["risk_weight"] = 1.5
            focus["opportunity_weight"] = 0.7
            focus["conservative_bias"] = 0.1
        
        if any(kw in mission_lower for kw in ["alpha", "aggressive", "growth", "maximize", "opportunity"]):
            focus["risk_weight"] = 0.7
            focus["opportunity_weight"] = 1.5
            focus["conservative_bias"] = -0.1
        
        if any(kw in mission_lower for kw in ["constraint", "limit", "strict"]):
            focus["conservative_bias"] += 0.15
        
        return focus

    # -------------------------------------------------------------------------
    # Policy Versioning (§3.4 - strategy evolution)
    # -------------------------------------------------------------------------

    def update_policy_version(self, reason: str) -> None:
        """§3.4: Increment policy version when strategy evolves.
        
        Policy versioning tracks how the agent's approach changes over time.
        Examples: 'Shifted to defensive mode after drawdown'
        """
        self.state.policy_version += 1
        logger.info(
            "[%s] Policy version updated to v%d: %s",
            self.agent_id, self.state.policy_version, reason
        )

    def should_shift_strategy(self) -> Optional[str]:
        """Check decision trajectory to determine if strategy shift is needed.
        
        Returns reason for shift, or None if no shift needed.
        """
        trajectory = self.state.decision_trajectory
        if len(trajectory) < 2:
            return None
        
        # Check for consecutive escalations - may need to become more conservative
        recent = trajectory[-3:] if len(trajectory) >= 3 else trajectory
        escalation_count = sum(1 for r in recent if r.outcome == "ESCALATED")
        
        if escalation_count >= 2:
            return "Multiple escalations detected - shifting to conservative mode"
        
        # Check for low confidence decisions
        low_confidence_count = sum(1 for r in recent if r.policy_confidence < 0.7)
        if low_confidence_count >= 2:
            return "Persistent uncertainty - increasing caution"
        
        return None

    # -------------------------------------------------------------------------
    # Decision Lifecycle (§4)
    # -------------------------------------------------------------------------

    @abstractmethod
    def explain(self, dfid: str, context: Dict[str, Any]) -> ExplainResult:
        """§4.1: Interpret context and make sense of the situation.
        
        Answers: 'What is happening, and why does it matter for my mission?'
        """
        pass

    @abstractmethod
    def formulate_policy(self, dfid: str, explain_result: ExplainResult) -> Policy:
        """§4.2: Propose a course of action based on interpretation.
        
        Returns structured recommendation with justification and confidence.
        """
        pass

    def self_check(self, policy: Policy) -> SelfCheckResult:
        """§4.3: Validate policy against agent's own boundaries.
        
        Self-Check is a cost-optimization heuristic - catches obvious issues
        before reaching the Runtime. Has no security value.
        """
        # Check confidence threshold for escalation
        if policy.confidence < self.contract.escalate_on_uncertainty:
            return SelfCheckResult(
                passed=False,
                reason=f"Confidence {policy.confidence:.2f} below threshold {self.contract.escalate_on_uncertainty}",
                should_escalate=True,
                escalation_trigger="uncertainty_threshold",
            )
        
        # Check if proposed action is within allowed policy types
        if self.contract.allowed_policy_types:
            action_type = policy.proposed_action.split(":")[0] if ":" in policy.proposed_action else policy.proposed_action
            if action_type not in self.contract.allowed_policy_types:
                return SelfCheckResult(
                    passed=False,
                    reason=f"Action type '{action_type}' not in allowed types: {self.contract.allowed_policy_types}",
                    should_escalate=True,
                    escalation_trigger="authority_breach",
                )
        
        return SelfCheckResult(passed=True)

    def emit_proposal(self, dfid: str, policy: Policy) -> PolicyProposal:
        """§4.4: Convert validated policy into a PolicyProposal for the Runtime."""
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy.proposed_action,
            params={
                "assumptions": policy.assumptions,
                "expected_outcomes": policy.expected_outcomes,
            },
            confidence=policy.confidence,
            justification=policy.justification,
            explain_ref=policy.explain_ref,
        )

    def create_escalation(self, dfid: str, policy: Policy, trigger: str) -> EscalationRequest:
        """§5.3: Create escalation request when limits are reached."""
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
        """§3.4: Update decision trajectory in agent state."""
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

    # -------------------------------------------------------------------------
    # Full Decision Cycle
    # -------------------------------------------------------------------------

    def run_decision_cycle(
        self, dfid: str, context: Dict[str, Any]
    ) -> Union[PolicyProposal, EscalationRequest]:
        """Execute full ROA decision cycle: Explain → Policy → Self-Check → Proposal/Escalation."""
        
        log_with_dfid(logger, dfid, logging.INFO, "[%s] Starting decision cycle", self.agent_id)
        
        # 1. Explain (§4.1)
        explain_result = self.explain(dfid, context)
        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Explain: %d signals, %d risks, %d opportunities",
            self.agent_id,
            len(explain_result.identified_signals),
            len(explain_result.risks),
            len(explain_result.opportunities),
        )
        
        # 2. Policy (§4.2)
        policy = self.formulate_policy(dfid, explain_result)
        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Policy: action='%s' confidence=%.2f",
            self.agent_id, policy.proposed_action, policy.confidence,
        )
        
        # 3. Self-Check (§4.3)
        check_result = self.self_check(policy)
        
        if not check_result.passed:
            log_with_dfid(
                logger, dfid, logging.WARNING,
                "[%s] Self-check FAILED: %s (escalate=%s)",
                self.agent_id, check_result.reason, check_result.should_escalate,
            )
            
            if check_result.should_escalate:
                self.record_decision(dfid, explain_result, policy, "ESCALATED", check_result.reason)
                return self.create_escalation(dfid, policy, check_result.escalation_trigger or "unknown")
            else:
                # Abort without escalation
                self.record_decision(dfid, explain_result, policy, "REJECTED", check_result.reason)
                raise ValueError(f"Policy rejected: {check_result.reason}")
        
        # 4. Emit Proposal (§4.4)
        proposal = self.emit_proposal(dfid, policy)
        self.record_decision(dfid, explain_result, policy, "ACCEPTED")
        
        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] Proposal emitted: kind=%s confidence=%.2f",
            self.agent_id, proposal.policy_kind, proposal.confidence,
        )
        
        return proposal

    # -------------------------------------------------------------------------
    # State Persistence (§3.4 - Long-lived agents with memory)
    # -------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent state to dictionary for persistence.
        
        Includes contract, state (with trajectory), and agent-specific data.
        """
        return {
            "agent_type": self.__class__.__name__,
            "contract": self.contract.model_dump(mode="json"),
            "state": self.state.model_dump(mode="json"),
            "child_agents": {
                agent_id: child.to_dict()
                for agent_id, child in self._child_agents.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ROAAgent":
        """Restore agent from dictionary.
        
        Note: Subclasses should override this to restore agent-specific fields.
        """
        contract = ResponsibilityContract(**data["contract"])
        agent = cls(contract)  # type: ignore
        agent.state = AgentState(**data["state"])
        return agent

    def save_state(self, path: Path | str) -> None:
        """Save agent state to JSON file.
        
        Persists the full agent state including:
        - Responsibility contract
        - Decision trajectory (memory)
        - Child agents
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        
        logger.info("[%s] State saved to %s", self.agent_id, path)

    @classmethod
    def load_state(cls, path: Path | str) -> "ROAAgent":
        """Load agent state from JSON file.
        
        Restores the agent with its full decision trajectory.
        """
        path = Path(path)
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        agent = cls.from_dict(data)
        logger.info("[%s] State loaded from %s (trajectory: %d decisions)",
                    agent.agent_id, path, len(agent.state.decision_trajectory))
        return agent


# =============================================================================
# InstrumentAgent - Class-Level Agent (Manifesto §6.1-6.2)
# =============================================================================


class InstrumentAgent(ROAAgent):
    """Class-level agent responsible for a specific instrument.
    
    Mission: Interpret market signals and manage positions for the instrument.
    Can spawn PositionAgent instances when new positions are opened (§6.1).
    """

    def __init__(self, instrument: str, contract: Optional[ResponsibilityContract] = None):
        self.instrument = instrument
        
        if contract is None:
            contract = ResponsibilityContract(
                agent_id=f"instrument_{instrument.lower().replace('-', '_')}",
                role="STRATEGIST",
                mission=f"Interpret market signals and manage positions for {instrument}",
                authorized_instruments=[instrument],
                allowed_policy_types=["OPEN_POSITION", "CLOSE_POSITION", "ADJUST_RISK", "HOLD"],
                escalate_on_uncertainty=0.65,
                max_drawdown_limit=0.05,
            )
        
        super().__init__(contract)
        self._position_agents: Dict[str, PositionAgent] = {}

    # -------------------------------------------------------------------------
    # State Persistence Override
    # -------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize InstrumentAgent with instrument field."""
        data = super().to_dict()
        data["instrument"] = self.instrument
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstrumentAgent":
        """Restore InstrumentAgent from dictionary."""
        instrument = data.get("instrument", "UNKNOWN")
        contract = ResponsibilityContract(**data["contract"])
        agent = cls(instrument=instrument, contract=contract)
        agent.state = AgentState(**data["state"])
        return agent

    def explain(self, dfid: str, context: Dict[str, Any]) -> ExplainResult:
        """§4.1: Interpret market context through the lens of mission.
        
        Mission actively influences interpretation - not just a label.
        """
        # Get mission-driven focus weights
        focus = self.parse_mission_focus()
        
        # Mock market interpretation (in real system: LLM or signal processing)
        price = context.get("price", 50000)
        volatility = context.get("volatility", 0.02)
        trend = context.get("trend", "neutral")
        
        signals = []
        risks = []
        opportunities = []
        
        # Apply mission-driven interpretation
        # Risk-focused missions are more sensitive to volatility
        volatility_threshold = 0.03 if focus["risk_weight"] <= 1.0 else 0.025
        
        if volatility > volatility_threshold:
            signals.append("HIGH_VOLATILITY")
            # Risk-focused missions emphasize this more
            if focus["risk_weight"] > 1.0:
                risks.append(f"HIGH PRIORITY: Volatility {volatility:.2%} exceeds mission threshold")
            else:
                risks.append("Increased risk due to high volatility")
        
        if trend == "bullish":
            signals.append("BULLISH_TREND")
            # Opportunity-focused missions emphasize upside more
            if focus["opportunity_weight"] > 1.0:
                opportunities.append("STRONG SIGNAL: Trend continuation - aligns with growth mission")
            else:
                opportunities.append("Trend continuation potential")
        elif trend == "bearish":
            signals.append("BEARISH_TREND")
            risks.append("Downside risk from bearish momentum")
        
        if price > context.get("resistance", 60000):
            signals.append("BREAKOUT_ABOVE_RESISTANCE")
            opportunities.append("Breakout trade opportunity")
        
        # Mission-driven narrative framing
        mission_lens = (
            "Through risk-protection lens" if focus["risk_weight"] > 1.0
            else "Through growth-opportunity lens" if focus["opportunity_weight"] > 1.0
            else "With balanced assessment"
        )
        
        narrative = (
            f"[Mission: {self.contract.mission[:40]}...] "
            f"{mission_lens}: {self.instrument} at {price}, volatility={volatility:.2%}, trend={trend}. "
            f"Identified {len(risks)} risks (weight={focus['risk_weight']:.1f}x), "
            f"{len(opportunities)} opportunities (weight={focus['opportunity_weight']:.1f}x). "
            f"Policy version: v{self.state.policy_version}."
        )
        
        return ExplainResult(
            dfid=dfid,
            agent_id=self.agent_id,
            narrative=narrative,
            identified_signals=signals,
            risks=risks,
            opportunities=opportunities,
            context_summary={
                "price": price, 
                "volatility": volatility, 
                "trend": trend,
                "mission_focus": focus,
                "policy_version": self.state.policy_version,
            },
        )

    def formulate_policy(self, dfid: str, explain_result: ExplainResult) -> Policy:
        """§4.2: Formulate policy influenced by mission focus and policy version."""
        
        signals = explain_result.identified_signals
        risks = explain_result.risks
        opportunities = explain_result.opportunities
        focus = explain_result.context_summary.get("mission_focus", {})
        conservative_bias = focus.get("conservative_bias", 0.0)
        
        # Check if strategy shift is needed based on trajectory
        shift_reason = self.should_shift_strategy()
        if shift_reason:
            self.update_policy_version(shift_reason)
            conservative_bias += 0.15  # Become more conservative after shift
        
        # Policy logic influenced by mission focus
        if "BREAKOUT_ABOVE_RESISTANCE" in signals and len(risks) < 2:
            action = "OPEN_POSITION"
            # Confidence adjusted by conservative bias
            confidence = max(0.5, 0.82 - conservative_bias)
            justification = f"Breakout detected (policy v{self.state.policy_version})"
        elif "HIGH_VOLATILITY" in signals:
            action = "HOLD"
            # Risk-focused missions are more cautious
            confidence = max(0.4, 0.55 - conservative_bias)
            justification = f"High volatility - conservative per mission (policy v{self.state.policy_version})"
        elif "BEARISH_TREND" in signals:
            action = "CLOSE_POSITION"
            confidence = 0.75 + conservative_bias  # More confident to close if conservative
            justification = f"Reduce exposure (policy v{self.state.policy_version})"
        else:
            action = "HOLD"
            confidence = 0.85
            justification = f"Maintain positions (policy v{self.state.policy_version})"
        
        return Policy(
            dfid=dfid,
            agent_id=self.agent_id,
            proposed_action=action,
            justification=justification,
            confidence=confidence,
            assumptions=[
                "Market data is current and reliable",
                f"Volatility remains within bounds (< {self.contract.max_drawdown_limit:.0%} drawdown)",
            ],
            expected_outcomes=[
                f"{'New position opened' if action == 'OPEN_POSITION' else 'Position maintained'}"
            ],
            explain_ref=dfid,
        )

    # -------------------------------------------------------------------------
    # Dynamic Agent Spawning (§6.1)
    # -------------------------------------------------------------------------

    def spawn_position_agent(self, position_id: str, entry_context: Dict[str, Any]) -> PositionAgent:
        """§6.1: Dynamically create instance-level agent for a specific position.
        
        PositionAgent has its own mission, state, and trajectory - isolated from others.
        """
        position_agent = PositionAgent(
            position_id=position_id,
            instrument=self.instrument,
            parent_agent_id=self.agent_id,
            entry_context=entry_context,
        )
        self._position_agents[position_id] = position_agent
        return position_agent

    def retire_position_agent(self, position_id: str) -> Optional[AgentState]:
        """Retire a position agent when position is closed. Returns final state."""
        if position_id in self._position_agents:
            agent = self._position_agents.pop(position_id)
            agent.state.is_active = False
            return agent.state
        return None


# =============================================================================
# PositionAgent - Instance-Level Agent (Manifesto §6.1, §6.3)
# =============================================================================


class PositionAgent(ROAAgent):
    """Instance-level agent managing a specific position.
    
    Created dynamically by InstrumentAgent when a position is opened.
    Has its own mission, state, and lifecycle - isolated from other positions.
    Exists only as long as the position is open (§6.3).
    """

    def __init__(
        self,
        position_id: str,
        instrument: str,
        parent_agent_id: str,
        entry_context: Dict[str, Any],
    ):
        self.position_id = position_id
        self.instrument = instrument
        self.entry_price = entry_context.get("entry_price", 0)
        self.entry_time = datetime.now(timezone.utc)
        
        contract = ResponsibilityContract(
            agent_id=f"position_{position_id}",
            role="EXECUTOR",
            mission=f"Manage position {position_id} on {instrument} according to risk constraints",
            authorized_instruments=[instrument],
            allowed_policy_types=["ADJUST_STOP", "TAKE_PROFIT", "CLOSE", "HOLD"],
            escalate_on_uncertainty=0.60,
            max_drawdown_limit=0.03,  # Tighter limit for position-level
            parent_agent_id=parent_agent_id,
        )
        
        super().__init__(contract)
        self.state.current_context = entry_context

    def explain(self, dfid: str, context: Dict[str, Any]) -> ExplainResult:
        """§4.1: Interpret context through mission lens - position-specific."""
        
        # Get mission-driven focus (position missions emphasize risk constraints)
        focus = self.parse_mission_focus()
        
        current_price = context.get("price", self.entry_price)
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.entry_price else 0
        
        signals = []
        risks = []
        opportunities = []
        
        # Mission-adjusted thresholds
        # Risk-focused missions use tighter profit targets and earlier drawdown warnings
        profit_threshold = 0.05 if focus["risk_weight"] <= 1.0 else 0.04
        drawdown_warning = -0.02 if focus["risk_weight"] <= 1.0 else -0.015
        
        if pnl_pct > profit_threshold:
            signals.append("PROFIT_TARGET_NEAR")
            if focus["risk_weight"] > 1.0:
                opportunities.append(f"PRIORITY: Lock profits - mission emphasizes capital protection")
            else:
                opportunities.append("Consider taking partial profits")
        elif pnl_pct < drawdown_warning:
            signals.append("DRAWDOWN_WARNING")
            if focus["risk_weight"] > 1.0:
                risks.append(f"ALERT: Position drawdown {pnl_pct:.2%} - risk mission triggered")
            else:
                risks.append(f"Position drawdown: {pnl_pct:.2%}")
        
        if pnl_pct < -self.contract.max_drawdown_limit:
            signals.append("MAX_DRAWDOWN_BREACH")
            risks.append("CRITICAL: Risk limit exceeded - immediate action required")
        
        narrative = (
            f"[Mission: {self.contract.mission[:35]}...] "
            f"Position {self.position_id}: entry={self.entry_price}, current={current_price}, PnL={pnl_pct:.2%}. "
            f"Risk weight={focus['risk_weight']:.1f}x. Policy v{self.state.policy_version}. "
            f"{'RISK LIMIT BREACHED' if pnl_pct < -self.contract.max_drawdown_limit else 'Within limits'}."
        )
        
        return ExplainResult(
            dfid=dfid,
            agent_id=self.agent_id,
            narrative=narrative,
            identified_signals=signals,
            risks=risks,
            opportunities=opportunities,
            context_summary={
                "entry_price": self.entry_price, 
                "current_price": current_price, 
                "pnl_pct": pnl_pct,
                "mission_focus": focus,
                "policy_version": self.state.policy_version,
            },
        )

    def formulate_policy(self, dfid: str, explain_result: ExplainResult) -> Policy:
        """§4.2: Formulate position policy with mission influence."""
        
        signals = explain_result.identified_signals
        pnl_pct = explain_result.context_summary.get("pnl_pct", 0)
        focus = explain_result.context_summary.get("mission_focus", {})
        conservative_bias = focus.get("conservative_bias", 0.0)
        
        # Check for strategy shift
        shift_reason = self.should_shift_strategy()
        if shift_reason:
            self.update_policy_version(shift_reason)
            conservative_bias += 0.1
        
        if "MAX_DRAWDOWN_BREACH" in signals:
            action = "CLOSE"
            confidence = 0.95
            justification = f"Risk limit breached - mandatory close (policy v{self.state.policy_version})"
        elif "PROFIT_TARGET_NEAR" in signals:
            action = "TAKE_PROFIT"
            # Risk-focused missions more eager to lock profits
            confidence = min(0.95, 0.78 + conservative_bias)
            justification = f"Secure gains per mission (policy v{self.state.policy_version})"
        elif "DRAWDOWN_WARNING" in signals:
            action = "ADJUST_STOP"
            confidence = 0.70 + conservative_bias
            justification = f"Tighten stop - mission risk focus (policy v{self.state.policy_version})"
        else:
            action = "HOLD"
            confidence = 0.85
            justification = f"Within parameters (policy v{self.state.policy_version})"
        
        return Policy(
            dfid=dfid,
            agent_id=self.agent_id,
            proposed_action=action,
            justification=justification,
            confidence=confidence,
            assumptions=[f"Current PnL: {pnl_pct:.2%}"],
            expected_outcomes=[f"Position {'closed' if action == 'CLOSE' else 'maintained'}"],
            explain_ref=dfid,
        )


# =============================================================================
# Main: Full ROA Demonstration
# =============================================================================


def main() -> None:
    """Demonstrate full ROA lifecycle with dynamic agents and escalation scenarios."""
    
    print("=" * 70)
    print("ROA Agent Sample - Full Lifecycle Demonstration")
    print("=" * 70)
    
    # -------------------------------------------------------------------------
    # Scenario A: Normal flow - high confidence, proposal emitted
    # -------------------------------------------------------------------------
    
    print("\n[SCENARIO A] Normal decision flow - breakout opportunity\n")
    
    dfid_a = new_dfid()
    log_with_dfid(logger, dfid_a, logging.INFO, "Starting Scenario A: Normal flow")
    
    # Create InstrumentAgent (class-level)
    btc_agent = InstrumentAgent("BTC-USD")
    log_with_dfid(
        logger, dfid_a, logging.INFO,
        "Created InstrumentAgent: %s, mission='%s'",
        btc_agent.agent_id, btc_agent.contract.mission[:50] + "...",
    )
    
    # Market context with breakout signal
    context_a = {
        "price": 62000,
        "volatility": 0.02,
        "trend": "bullish",
        "resistance": 60000,
    }
    
    result_a = btc_agent.run_decision_cycle(dfid_a, context_a)
    
    if isinstance(result_a, PolicyProposal):
        print(f"\n[RESULT A] PolicyProposal emitted:")
        print(f"  DFID: {result_a.dfid}")
        print(f"  Agent: {result_a.agent_id}")
        print(f"  Action: {result_a.policy_kind}")
        print(f"  Confidence: {result_a.confidence:.2f}")
        print(f"  Justification: {result_a.justification}")
    
    # -------------------------------------------------------------------------
    # Scenario B: Low confidence - escalation triggered
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO B] Low confidence - escalation to human/supervisor\n")
    
    dfid_b = new_dfid()
    log_with_dfid(logger, dfid_b, logging.INFO, "Starting Scenario B: High volatility")
    
    # High volatility context - will trigger uncertainty escalation
    context_b = {
        "price": 55000,
        "volatility": 0.05,  # High volatility
        "trend": "neutral",
        "resistance": 60000,
    }
    
    result_b = btc_agent.run_decision_cycle(dfid_b, context_b)
    
    if isinstance(result_b, EscalationRequest):
        print(f"\n[RESULT B] EscalationRequest emitted:")
        print(f"  DFID: {result_b.dfid}")
        print(f"  From: {result_b.from_agent_id}")
        print(f"  Trigger: {result_b.trigger}")
        print(f"  Severity: {result_b.severity}")
        print(f"  Original policy: {result_b.original_policy.proposed_action if result_b.original_policy else 'N/A'}")
    
    # -------------------------------------------------------------------------
    # Scenario C: Dynamic PositionAgent - instance-level agent
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO C] Dynamic PositionAgent - managing specific position\n")
    
    dfid_c = new_dfid()
    log_with_dfid(logger, dfid_c, logging.INFO, "Starting Scenario C: Position management")
    
    # Spawn PositionAgent (instance-level, created dynamically)
    position_agent = btc_agent.spawn_position_agent(
        position_id="POS_001",
        entry_context={"entry_price": 60000, "size": 0.5},
    )
    
    log_with_dfid(
        logger, dfid_c, logging.INFO,
        "Spawned PositionAgent: %s (parent=%s)",
        position_agent.agent_id,
        position_agent.contract.parent_agent_id,
    )
    
    # Position is in profit
    context_c = {"price": 63500}  # +5.8% profit
    
    result_c = position_agent.run_decision_cycle(dfid_c, context_c)
    
    if isinstance(result_c, PolicyProposal):
        print(f"\n[RESULT C] PositionAgent PolicyProposal:")
        print(f"  DFID: {result_c.dfid}")
        print(f"  Agent: {result_c.agent_id}")
        print(f"  Action: {result_c.policy_kind}")
        print(f"  Confidence: {result_c.confidence:.2f}")
        print(f"  Justification: {result_c.justification}")
    
    # -------------------------------------------------------------------------
    # Scenario D: Position drawdown - risk limit breach
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO D] Position drawdown - risk limit forces action\n")
    
    dfid_d = new_dfid()
    log_with_dfid(logger, dfid_d, logging.INFO, "Starting Scenario D: Drawdown scenario")
    
    # Price dropped significantly - risk limit breached
    context_d = {"price": 57500}  # -4.2% loss, exceeds 3% max_drawdown_limit
    
    result_d = position_agent.run_decision_cycle(dfid_d, context_d)
    
    if isinstance(result_d, PolicyProposal):
        print(f"\n[RESULT D] Risk-triggered PolicyProposal:")
        print(f"  Action: {result_d.policy_kind}")
        print(f"  Confidence: {result_d.confidence:.2f}")
        print(f"  Justification: {result_d.justification}")
    
    # Retire position agent after close
    final_state = btc_agent.retire_position_agent("POS_001")
    if final_state:
        log_with_dfid(
            logger, dfid_d, logging.INFO,
            "PositionAgent retired. Trajectory: %d decisions",
            len(final_state.decision_trajectory),
        )
    
    # -------------------------------------------------------------------------
    # Summary: Agent Memory/Trajectory
    # -------------------------------------------------------------------------
    
    print("\n" + "=" * 70)
    print("[SUMMARY] Agent Decision Trajectories")
    print("=" * 70)
    
    print(f"\nInstrumentAgent ({btc_agent.agent_id}):")
    print(f"  Total decisions: {len(btc_agent.state.decision_trajectory)}")
    for i, record in enumerate(btc_agent.state.decision_trajectory):
        print(f"  [{i+1}] DFID={record.dfid[:12]}... action={record.policy_action} "
              f"confidence={record.policy_confidence:.2f} outcome={record.outcome}")
    
    if final_state:
        print(f"\nPositionAgent ({final_state.agent_id}) - RETIRED:")
        print(f"  Total decisions: {len(final_state.decision_trajectory)}")
        for i, record in enumerate(final_state.decision_trajectory):
            print(f"  [{i+1}] DFID={record.dfid[:12]}... action={record.policy_action} "
                  f"confidence={record.policy_confidence:.2f} outcome={record.outcome}")
    
    # -------------------------------------------------------------------------
    # Scenario E: State Persistence - Save and Load Agent
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO E] State Persistence - Save and Load Agent\n")
    
    # Save the InstrumentAgent state (with its decision trajectory)
    state_file = Path("samples/01_roa/data/btc_agent_state.json")
    btc_agent.save_state(state_file)
    print(f"  Saved agent state to: {state_file}")
    print(f"  Trajectory before save: {len(btc_agent.state.decision_trajectory)} decisions")
    
    # Simulate "restart" - create new agent from saved state
    print("\n  --- Simulating restart: loading agent from file ---\n")
    
    restored_agent = InstrumentAgent.load_state(state_file)
    
    print(f"  Restored agent: {restored_agent.agent_id}")
    print(f"  Mission: {restored_agent.contract.mission[:50]}...")
    print(f"  Trajectory restored: {len(restored_agent.state.decision_trajectory)} decisions")
    
    # Run another decision cycle with restored agent
    dfid_e = new_dfid()
    log_with_dfid(logger, dfid_e, logging.INFO, "Running decision with restored agent")
    
    context_e = {
        "price": 65000,
        "volatility": 0.015,
        "trend": "bullish",
        "resistance": 64000,
    }
    
    result_e = restored_agent.run_decision_cycle(dfid_e, context_e)
    
    if isinstance(result_e, PolicyProposal):
        print(f"\n[RESULT E] Restored agent decision:")
        print(f"  Action: {result_e.policy_kind}")
        print(f"  Confidence: {result_e.confidence:.2f}")
    
    # Show trajectory now includes the new decision
    print(f"\n  Trajectory after new decision: {len(restored_agent.state.decision_trajectory)} decisions")
    
    # Save updated state
    restored_agent.save_state(state_file)
    print(f"  Updated state saved.")
    
    # Show the saved JSON content
    print(f"\n  Saved state file content (truncated):")
    with open(state_file, "r") as f:
        content = json.load(f)
        print(f"    agent_type: {content['agent_type']}")
        print(f"    agent_id: {content['contract']['agent_id']}")
        print(f"    decisions in trajectory: {len(content['state']['decision_trajectory'])}")
    
    # -------------------------------------------------------------------------
    # Scenario F: Mission-Driven Reasoning - Same context, different missions
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO F] Mission-Driven Reasoning - Same data, different interpretations\n")
    
    # Create two agents with different missions
    growth_agent = InstrumentAgent(
        "ETH-USD",
        contract=ResponsibilityContract(
            agent_id="eth_growth_agent",
            role="STRATEGIST",
            mission="Maximize alpha and capture growth opportunities aggressively",
            authorized_instruments=["ETH-USD"],
            allowed_policy_types=["OPEN_POSITION", "CLOSE_POSITION", "ADJUST_RISK", "HOLD"],
            escalate_on_uncertainty=0.50,  # Lower threshold - more aggressive
            max_drawdown_limit=0.08,
        )
    )
    
    defensive_agent = InstrumentAgent(
        "ETH-USD",
        contract=ResponsibilityContract(
            agent_id="eth_defensive_agent",
            role="STRATEGIST",
            mission="Protect capital and preserve value with strict risk limits",
            authorized_instruments=["ETH-USD"],
            allowed_policy_types=["OPEN_POSITION", "CLOSE_POSITION", "ADJUST_RISK", "HOLD"],
            escalate_on_uncertainty=0.75,  # Higher threshold - more cautious
            max_drawdown_limit=0.03,
        )
    )
    
    # Same market context for both
    same_context = {
        "price": 3500,
        "volatility": 0.028,  # Borderline volatility
        "trend": "bullish",
        "resistance": 3400,
    }
    
    print("  Same market context: price=3500, volatility=2.8%, trend=bullish")
    print("  Testing how mission influences interpretation:\n")
    
    dfid_f1 = new_dfid()
    log_with_dfid(logger, dfid_f1, logging.INFO, "Growth agent analyzing...")
    result_f1 = growth_agent.run_decision_cycle(dfid_f1, same_context)
    
    dfid_f2 = new_dfid()
    log_with_dfid(logger, dfid_f2, logging.INFO, "Defensive agent analyzing...")
    result_f2 = defensive_agent.run_decision_cycle(dfid_f2, same_context)
    
    print("\n  [COMPARISON] Same data, different missions:")
    print(f"\n  Growth Agent (mission: 'Maximize alpha...'):")
    print(f"    Focus: opportunity_weight={growth_agent.parse_mission_focus()['opportunity_weight']:.1f}x")
    if isinstance(result_f1, PolicyProposal):
        print(f"    Action: {result_f1.policy_kind}, Confidence: {result_f1.confidence:.2f}")
    elif isinstance(result_f1, EscalationRequest):
        print(f"    ESCALATED: {result_f1.trigger}")
    
    print(f"\n  Defensive Agent (mission: 'Protect capital...'):")
    print(f"    Focus: risk_weight={defensive_agent.parse_mission_focus()['risk_weight']:.1f}x")
    if isinstance(result_f2, PolicyProposal):
        print(f"    Action: {result_f2.policy_kind}, Confidence: {result_f2.confidence:.2f}")
    elif isinstance(result_f2, EscalationRequest):
        print(f"    ESCALATED: {result_f2.trigger}")
    
    # -------------------------------------------------------------------------
    # Scenario G: Policy Versioning - Strategy evolution after challenges
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO G] Policy Versioning - Strategy evolution after repeated challenges\n")
    
    # Create an agent that will experience multiple escalations
    evolving_agent = InstrumentAgent(
        "SOL-USD",
        contract=ResponsibilityContract(
            agent_id="sol_evolving_agent",
            role="STRATEGIST",
            mission="Balance risk and opportunity with adaptive strategy",
            authorized_instruments=["SOL-USD"],
            allowed_policy_types=["OPEN_POSITION", "CLOSE_POSITION", "ADJUST_RISK", "HOLD"],
            escalate_on_uncertainty=0.65,
            max_drawdown_limit=0.05,
        )
    )
    
    print(f"  Initial policy version: v{evolving_agent.state.policy_version}")
    
    # Run multiple challenging scenarios to trigger strategy evolution
    challenging_contexts = [
        {"price": 150, "volatility": 0.04, "trend": "neutral", "resistance": 160},  # High vol
        {"price": 145, "volatility": 0.045, "trend": "bearish", "resistance": 160}, # Worse
        {"price": 140, "volatility": 0.05, "trend": "bearish", "resistance": 160},  # Escalation
    ]
    
    for i, ctx in enumerate(challenging_contexts, 1):
        dfid_g = new_dfid()
        log_with_dfid(logger, dfid_g, logging.INFO, f"Challenge {i}: vol={ctx['volatility']:.1%}")
        result_g = evolving_agent.run_decision_cycle(dfid_g, ctx)
        
        outcome = "ESCALATED" if isinstance(result_g, EscalationRequest) else result_g.policy_kind
        print(f"  Challenge {i}: vol={ctx['volatility']:.1%} → {outcome} (policy v{evolving_agent.state.policy_version})")
    
    # After challenges, check if policy version evolved
    print(f"\n  Final policy version: v{evolving_agent.state.policy_version}")
    print(f"  Decision trajectory: {len(evolving_agent.state.decision_trajectory)} decisions")
    
    # Show how trajectory influenced the version change
    escalation_count = sum(1 for r in evolving_agent.state.decision_trajectory if r.outcome == "ESCALATED")
    print(f"  Escalations in history: {escalation_count}")
    print(f"  → Agent {'shifted to more conservative strategy' if evolving_agent.state.policy_version > 1 else 'maintained original strategy'}")


if __name__ == "__main__":
    main()
