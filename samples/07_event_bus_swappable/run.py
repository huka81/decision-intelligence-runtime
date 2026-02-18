#!/usr/bin/env python3
"""
07_event_bus_swappable - Event-Oriented Agent Mesh (EOAM) demonstration.

Shows:
- Multi-agent reactive activation via event subscriptions
- DFID correlation across event flow
- Scope-based routing (semantic filtering)
- Wake-up predicates (token burn prevention)
- Swappable backend pattern (factory)
- Full EOAM lifecycle: OBSERVATION → POLICY_PROPOSAL → VALIDATION → EXECUTION

DIR Topologies alignment: §2 (EOAM), §2.1-2.4 (choreography, routing, economic guardrails)

Run from repo root: python samples/07_event_bus_swappable/run.py
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from dir import (
    Event,
    EventBus,
    EventMetadata,
    EventType,
    LoggingEventBus,
    PolicyProposal,
    create_event_bus,
    new_dfid,
)
from dir.logging_utils import log_with_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# Wake-up Predicates (DIR Topologies §2.3)
# =============================================================================


@dataclass
class WakeupPredicate:
    """Low-cost heuristic to prevent Token Burn.
    
    Evaluated BEFORE activating expensive LLM agent.
    If predicate returns False, agent is not woken up.
    """
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    
    def evaluate(self, payload: Dict[str, Any]) -> bool:
        result = self.condition(payload)
        logger.debug("  Predicate '%s': %s", self.name, "PASS" if result else "SKIP")
        return result


# Common predicates
def price_change_significant(payload: Dict[str, Any], threshold: float = 0.005) -> bool:
    """Wake up only if price change > threshold (0.5% default)."""
    delta = abs(payload.get("price_delta_pct", 0))
    return delta > threshold


def volatility_elevated(payload: Dict[str, Any], threshold: float = 0.03) -> bool:
    """Wake up only if volatility is elevated."""
    return payload.get("volatility", 0) > threshold


def is_relevant_instrument(payload: Dict[str, Any], instruments: List[str]) -> bool:
    """Wake up only for specific instruments."""
    return payload.get("instrument") in instruments


# =============================================================================
# Reactive Agent (EOAM pattern)
# =============================================================================


class ReactiveAgent:
    """Agent that reacts to events on the bus (DIR Topologies §2.1).
    
    EOAM principle: "Decentralized in activation, centralized in authority."
    Agents subscribe to topics matching their Responsibility Contract scope.
    """
    
    def __init__(
        self, 
        agent_id: str, 
        scope: Optional[str] = None,
        wakeup_predicates: Optional[List[WakeupPredicate]] = None,
    ):
        self.agent_id = agent_id
        self.scope = scope
        self.wakeup_predicates = wakeup_predicates or []
        self._event_count = 0
        self._activated_count = 0
        self._suppressed_count = 0
    
    def should_wake(self, payload: Dict[str, Any]) -> bool:
        """Evaluate all wake-up predicates. All must pass."""
        for predicate in self.wakeup_predicates:
            if not predicate.evaluate(payload):
                return False
        return True
    
    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        """Handle OBSERVATION event - the main reactive entry point."""
        self._event_count += 1
        dfid = payload.get("dfid", "unknown")
        
        # Check wake-up predicates
        if self.wakeup_predicates and not self.should_wake(payload):
            self._suppressed_count += 1
            log_with_dfid(logger, dfid, logging.DEBUG, 
                         f"[{self.agent_id}] Suppressed by wake-up predicate")
            return None
        
        self._activated_count += 1
        log_with_dfid(logger, dfid, logging.INFO, 
                     f"[{self.agent_id}] Activated on OBSERVATION")
        
        # Simulate reasoning and emit proposal
        proposal = self.reason(dfid, payload)
        return proposal
    
    def reason(self, dfid: str, context: Dict[str, Any]) -> PolicyProposal:
        """Agent-specific reasoning logic."""
        # Override in subclasses for specific behavior
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind="HOLD",
            params={"reason": f"Default response from {self.agent_id}"},
            confidence=0.7,
        )
    
    def get_stats(self) -> Dict[str, int]:
        return {
            "events_received": self._event_count,
            "activated": self._activated_count,
            "suppressed": self._suppressed_count,
        }


class RiskMonitorAgent(ReactiveAgent):
    """Monitors for risk alerts - high priority."""
    
    def reason(self, dfid: str, context: Dict[str, Any]) -> PolicyProposal:
        volatility = context.get("volatility", 0)
        if volatility > 0.04:
            return PolicyProposal(
                dfid=dfid,
                agent_id=self.agent_id,
                policy_kind="RISK_ALERT",
                params={"volatility": volatility, "action": "reduce_exposure"},
                confidence=0.90,
            )
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind="RISK_OK",
            params={"volatility": volatility},
            confidence=0.85,
        )


class TechnicalAnalysisAgent(ReactiveAgent):
    """Technical analysis signals."""
    
    def reason(self, dfid: str, context: Dict[str, Any]) -> PolicyProposal:
        trend = context.get("trend", "neutral")
        price_delta = context.get("price_delta_pct", 0)
        
        if trend == "bullish" and price_delta > 0.01:
            action = "OPEN_LONG"
            confidence = 0.75
        elif trend == "bearish" and price_delta < -0.01:
            action = "CLOSE_LONG"
            confidence = 0.70
        else:
            action = "HOLD"
            confidence = 0.60
        
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=action,
            params={"trend": trend, "delta": price_delta},
            confidence=confidence,
        )


class SentimentAgent(ReactiveAgent):
    """Sentiment analysis - may have expensive LLM calls."""
    
    def reason(self, dfid: str, context: Dict[str, Any]) -> PolicyProposal:
        # Simulated sentiment (in reality would call LLM)
        sentiment = context.get("sentiment_score", 0.5)
        
        if sentiment > 0.7:
            action = "SENTIMENT_BULLISH"
        elif sentiment < 0.3:
            action = "SENTIMENT_BEARISH"
        else:
            action = "SENTIMENT_NEUTRAL"
        
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=action,
            params={"sentiment_score": sentiment},
            confidence=0.65,
        )


# =============================================================================
# EOAM Orchestrator
# =============================================================================


class EOAMOrchestrator:
    """Coordinates the Event-Oriented Agent Mesh.
    
    Implements Priority-Based Preemption Model (DIR Topologies §2.4):
    - Collects proposals from parallel agents
    - Applies priority matrix to select winner
    - High-priority agents (Risk) can preempt strategy proposals
    """
    
    PRIORITY_MATRIX = {
        "RISK_ALERT": 1,      # Highest - always wins
        "CLOSE_LONG": 2,
        "RISK_OK": 5,
        "OPEN_LONG": 3,
        "HOLD": 6,
        "SENTIMENT_BULLISH": 4,
        "SENTIMENT_BEARISH": 4,
        "SENTIMENT_NEUTRAL": 7,
    }
    
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.agents: List[ReactiveAgent] = []
        self._pending_proposals: Dict[str, List[PolicyProposal]] = {}  # dfid -> proposals
    
    def register_agent(self, agent: ReactiveAgent) -> None:
        """Register agent and subscribe to relevant events."""
        self.agents.append(agent)
        
        # Wrap handler to capture proposals
        def handler(payload: Dict[str, Any]) -> None:
            proposal = agent.on_observation(payload)
            if proposal:
                dfid = payload.get("dfid", "unknown")
                if dfid not in self._pending_proposals:
                    self._pending_proposals[dfid] = []
                self._pending_proposals[dfid].append(proposal)
        
        self.bus.subscribe(EventType.OBSERVATION, handler, scope=agent.scope)
    
    def emit_observation(
        self, 
        payload: Dict[str, Any], 
        dfid: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> str:
        """Emit observation and collect proposals."""
        dfid = dfid or new_dfid()
        payload["dfid"] = dfid
        
        metadata = EventMetadata(
            dfid=dfid,
            target_scope=scope,
            source_agent="orchestrator",
        )
        
        self.bus.publish(EventType.OBSERVATION, payload, metadata)
        return dfid
    
    def arbitrate(self, dfid: str) -> Optional[PolicyProposal]:
        """Select winning proposal using Priority Matrix (Topologies §2.4)."""
        proposals = self._pending_proposals.get(dfid, [])
        if not proposals:
            return None
        
        # Sort by priority (lower = higher priority)
        def get_priority(p: PolicyProposal) -> int:
            return self.PRIORITY_MATRIX.get(p.policy_kind, 10)
        
        sorted_proposals = sorted(proposals, key=get_priority)
        winner = sorted_proposals[0]
        
        log_with_dfid(logger, dfid, logging.INFO, 
                     f"Arbitration: {len(proposals)} proposals → winner: {winner.policy_kind} "
                     f"from {winner.agent_id} (priority={get_priority(winner)})")
        
        return winner
    
    def run_cycle(
        self, 
        observation: Dict[str, Any],
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run full EOAM cycle: observe → parallel reasoning → arbitrate."""
        dfid = self.emit_observation(observation, scope=scope)
        
        # In real async system, would wait for collection window
        # Here synchronous, so proposals are already collected
        
        winner = self.arbitrate(dfid)
        
        result = {
            "dfid": dfid,
            "proposals_count": len(self._pending_proposals.get(dfid, [])),
            "winner": winner.model_dump() if winner else None,
        }
        
        # Emit winning proposal
        if winner:
            self.bus.publish(
                EventType.POLICY_PROPOSAL,
                winner.model_dump(),
                EventMetadata(dfid=dfid, source_agent=winner.agent_id),
            )
        
        # Cleanup
        self._pending_proposals.pop(dfid, None)
        
        return result


# =============================================================================
# Main Demonstration
# =============================================================================


def main() -> None:
    print("=" * 70)
    print("Event Bus Sample - Event-Oriented Agent Mesh (EOAM)")
    print("=" * 70)
    
    # -------------------------------------------------------------------------
    # Scenario A: Basic Multi-Agent Reactive Flow
    # -------------------------------------------------------------------------
    
    print("\n[SCENARIO A] Multi-agent reactive activation\n")
    
    bus = create_event_bus(backend="memory")
    orchestrator = EOAMOrchestrator(bus)
    
    # Register agents with different roles
    risk_agent = RiskMonitorAgent("risk_monitor")
    tech_agent = TechnicalAnalysisAgent("technical_agent")
    sentiment_agent = SentimentAgent("sentiment_agent")
    
    orchestrator.register_agent(risk_agent)
    orchestrator.register_agent(tech_agent)
    orchestrator.register_agent(sentiment_agent)
    
    # Emit observation - all agents activated
    observation = {
        "instrument": "BTC-USD",
        "price": 67500,
        "price_delta_pct": 0.02,
        "volatility": 0.025,
        "trend": "bullish",
        "sentiment_score": 0.75,
    }
    
    result = orchestrator.run_cycle(observation)
    
    print(f"  DFID: {result['dfid'][:12]}...")
    print(f"  Proposals collected: {result['proposals_count']}")
    if result['winner']:
        print(f"  Winner: {result['winner']['policy_kind']} from {result['winner']['agent_id']}")
    
    # -------------------------------------------------------------------------
    # Scenario B: Risk Preemption (Priority-Based)
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO B] Risk preemption - high volatility overrides strategy\n")
    
    # High volatility triggers risk alert
    high_vol_observation = {
        "instrument": "BTC-USD",
        "price": 65000,
        "price_delta_pct": -0.03,
        "volatility": 0.06,  # High volatility
        "trend": "bearish",
        "sentiment_score": 0.3,
    }
    
    result_b = orchestrator.run_cycle(high_vol_observation)
    
    print(f"  DFID: {result_b['dfid'][:12]}...")
    print(f"  Proposals: {result_b['proposals_count']}")
    if result_b['winner']:
        print(f"  Winner: {result_b['winner']['policy_kind']} (risk alert preempts other proposals)")
    
    # -------------------------------------------------------------------------
    # Scenario C: Wake-up Predicates (Token Burn Prevention)
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO C] Wake-up predicates - preventing Token Burn\n")
    
    bus_c = create_event_bus()
    orchestrator_c = EOAMOrchestrator(bus_c)
    
    # Agent with strict wake-up predicate
    expensive_agent = SentimentAgent(
        "expensive_llm_agent",
        wakeup_predicates=[
            WakeupPredicate(
                "significant_move",
                lambda p: abs(p.get("price_delta_pct", 0)) > 0.01
            ),
            WakeupPredicate(
                "btc_only",
                lambda p: p.get("instrument") == "BTC-USD"
            ),
        ]
    )
    
    # Generic agent without predicates
    cheap_agent = TechnicalAnalysisAgent("cheap_agent")
    
    orchestrator_c.register_agent(expensive_agent)
    orchestrator_c.register_agent(cheap_agent)
    
    # Small move - expensive agent should NOT wake up
    small_move = {
        "instrument": "BTC-USD",
        "price_delta_pct": 0.002,  # Only 0.2%
        "volatility": 0.02,
        "trend": "neutral",
    }
    
    result_small = orchestrator_c.run_cycle(small_move)
    
    print(f"  Small move (0.2%):")
    print(f"    Proposals: {result_small['proposals_count']}")
    print(f"    Expensive agent stats: {expensive_agent.get_stats()}")
    
    # Large move - expensive agent SHOULD wake up
    large_move = {
        "instrument": "BTC-USD",
        "price_delta_pct": 0.025,  # 2.5%
        "volatility": 0.03,
        "trend": "bullish",
        "sentiment_score": 0.8,
    }
    
    result_large = orchestrator_c.run_cycle(large_move)
    
    print(f"\n  Large move (2.5%):")
    print(f"    Proposals: {result_large['proposals_count']}")
    print(f"    Expensive agent stats: {expensive_agent.get_stats()}")
    print(f"    → Token Burn prevented: {expensive_agent.get_stats()['suppressed']} activations skipped")
    
    # -------------------------------------------------------------------------
    # Scenario D: Scope-Based Routing
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO D] Scope-based routing - instrument-specific agents\n")
    
    bus_d = create_event_bus()
    orchestrator_d = EOAMOrchestrator(bus_d)
    
    # BTC-specific agent
    btc_agent = TechnicalAnalysisAgent("btc_specialist", scope="BTC-USD")
    # ETH-specific agent
    eth_agent = TechnicalAnalysisAgent("eth_specialist", scope="ETH-USD")
    # Global agent (receives all)
    global_agent = RiskMonitorAgent("global_risk", scope="*")
    
    orchestrator_d.register_agent(btc_agent)
    orchestrator_d.register_agent(eth_agent)
    orchestrator_d.register_agent(global_agent)
    
    # BTC event - should reach btc_specialist and global_risk only
    btc_event = {"instrument": "BTC-USD", "volatility": 0.02, "price_delta_pct": 0.01, "trend": "bullish"}
    result_btc = orchestrator_d.run_cycle(btc_event, scope="BTC-USD")
    
    print(f"  BTC-USD event:")
    print(f"    Proposals: {result_btc['proposals_count']} (btc_specialist + global_risk)")
    
    # ETH event
    eth_event = {"instrument": "ETH-USD", "volatility": 0.03, "price_delta_pct": 0.02, "trend": "bullish"}
    result_eth = orchestrator_d.run_cycle(eth_event, scope="ETH-USD")
    
    print(f"  ETH-USD event:")
    print(f"    Proposals: {result_eth['proposals_count']} (eth_specialist + global_risk)")
    
    # -------------------------------------------------------------------------
    # Scenario E: Logging/Audit Wrapper
    # -------------------------------------------------------------------------
    
    print("\n" + "-" * 70)
    print("\n[SCENARIO E] Swappable backend - LoggingEventBus wrapper\n")
    
    inner_bus = EventBus(name="Core")
    logging_bus = LoggingEventBus(inner_bus)
    
    # Simple handler
    received = []
    def collector(payload):
        received.append(payload)
    
    logging_bus.subscribe(EventType.MARKET_SIGNAL, collector)
    
    # Publish events
    for i in range(3):
        logging_bus.publish(
            EventType.MARKET_SIGNAL,
            {"signal_id": i, "value": 100 + i},
            EventMetadata(dfid=new_dfid(), source_agent="signal_generator"),
        )
    
    print(f"  Events published: {logging_bus.event_count}")
    print(f"  Events in audit log: {len(logging_bus.get_event_log())}")
    print(f"  Events received by handler: {len(received)}")
    
    # =========================================================================
    # Summary
    # =========================================================================
    
    print("\n" + "=" * 70)
    print("[SUMMARY] EOAM Event Bus Demonstration")
    print("=" * 70)
    
    print("\n  Key EOAM concepts demonstrated:")
    print("  • Multi-agent reactive activation (Topologies §2.1)")
    print("  • Priority-Based Preemption - Risk > Strategy (Topologies §2.4)")
    print("  • Wake-up Predicates - Token Burn prevention (Topologies §2.3)")
    print("  • Scope-based semantic routing")
    print("  • Swappable backend pattern (factory + LoggingEventBus)")
    print("  • DFID correlation across event flow")
    
    print("\n  Swappable backends available:")
    print("    • create_event_bus('memory') - in-memory (current)")
    print("    • create_event_bus('kafka')  - future Kafka implementation")
    print("    • create_event_bus('pubsub') - future PubSub implementation")
    print("    • Set EVENT_BUS_BACKEND env var to override")


if __name__ == "__main__":
    main()
