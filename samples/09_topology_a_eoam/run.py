#!/usr/bin/env python3
"""
09_topology_a_eoam - Topology A: Event bus, parallel agents, DIM, mock execution.

DIR Topologies §2: EOAM with scope-based choreography, inversion of control,
priority-based preemption, and context snapshot.

Run from repo root: python samples/09_topology_a_eoam/run.py
Requires PYTHONPATH including workspace src/ (see .vscode/settings.json).
"""
import logging
from typing import Any, Dict, List, Optional

from dir_core import (
    EventBus,
    EventMetadata,
    EventType,
    PolicyProposal,
    new_dfid,
    validate_proposal,
)
from dir_core.intent_retry import IntentRetryGovernor
from dir_core.lifecycle import FlowStatus, transition
from utils.logging_utils import log_with_dfid
from utils.quote_generator import QuoteGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Priority matrix: lower = higher priority (Risk preempts Strategy)
PRIORITY_MATRIX: Dict[str, int] = {"ALERT": 1, "ADJUST": 2, "HOLD": 3}
DEFAULT_PRIORITY = 10  # Unknown policy kinds get lowest priority


def arbitrate_by_priority(proposals: List[PolicyProposal]) -> Optional[PolicyProposal]:
    """Select winner by priority matrix (highest priority wins)."""
    if not proposals:
        return None
    return min(
        proposals,
        key=lambda p: PRIORITY_MATRIX.get(p.policy_kind, DEFAULT_PRIORITY),
    )


class RiskAgent:
    """Reactive agent: subscribes to OBSERVATION, proposes ALERT or HOLD based on volatility."""

    def __init__(self, bus: EventBus, agent_id: str, scope: str):
        self.bus = bus
        self.agent_id = agent_id
        self.scope = scope
        bus.subscribe(EventType.OBSERVATION, self.on_observation, scope=scope)

    def on_observation(self, payload: dict) -> None:
        dfid = payload.get("dfid", "")
        context_ref = payload.get("context_ref", "")
        volatility = payload.get("volatility", 0.0)
        instrument = payload.get("instrument", "")

        # Simple logic: high volatility -> ALERT, else HOLD
        policy_kind = "ALERT" if volatility > 0.05 else "HOLD"
        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy_kind,
            params={"instrument": instrument, "volatility": volatility},
            context_ref=context_ref or None,
        )
        self.bus.publish(EventType.POLICY_PROPOSAL, {"proposal": proposal})
        log_with_dfid(logger, dfid, logging.DEBUG, "%s proposed %s", self.agent_id, policy_kind)


class StrategyAgent:
    """Reactive agent: subscribes to OBSERVATION, proposes ADJUST or HOLD based on trend."""

    def __init__(self, bus: EventBus, agent_id: str, scope: str):
        self.bus = bus
        self.agent_id = agent_id
        self.scope = scope
        bus.subscribe(EventType.OBSERVATION, self.on_observation, scope=scope)

    def on_observation(self, payload: dict) -> None:
        dfid = payload.get("dfid", "")
        context_ref = payload.get("context_ref", "")
        trend = payload.get("trend", "neutral")
        instrument = payload.get("instrument", "")

        # Simple logic: bullish -> ADJUST, else HOLD
        policy_kind = "ADJUST" if trend == "bullish" else "HOLD"
        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy_kind,
            params={"instrument": instrument, "trend": trend},
            context_ref=context_ref or None,
        )
        self.bus.publish(EventType.POLICY_PROPOSAL, {"proposal": proposal})
        log_with_dfid(logger, dfid, logging.DEBUG, "%s proposed %s", self.agent_id, policy_kind)


def main() -> None:
    dfid = new_dfid()
    log_with_dfid(logger, dfid, logging.INFO, "EOAM: Observation received")

    bus = EventBus()
    proposals: List[PolicyProposal] = []

    def collect_proposal(payload: dict) -> None:
        p = payload.get("proposal")
        if p is not None:
            proposals.append(p)

    # 1. Register reactive agents (scope-based subscription)
    scope = "BTC-USD"
    risk_agent = RiskAgent(bus, "agent_risk", scope)
    strategy_agent = StrategyAgent(bus, "agent_strategy", scope)

    # 2. Orchestrator collects POLICY_PROPOSAL
    bus.subscribe(EventType.POLICY_PROPOSAL, collect_proposal)

    # 3. Build context snapshot and observation payload
    quote_gen = QuoteGenerator(instrument=scope, initial_price=50000.0, volatility=0.03, seed=42)
    tick = quote_gen.next_tick()
    observation_payload: Dict[str, Any] = tick.to_payload()
    context_snapshot: Dict[str, Any] = {
        "instrument": scope,
        "price": observation_payload.get("price"),
        "volatility": observation_payload.get("volatility", 0),
        "risk_score": 0.1,
    }
    context_ref = f"ctx_{dfid[:8]}"
    observation_payload["dfid"] = dfid
    observation_payload["context_ref"] = context_ref

    # 4. Wake-up predicate (DIR Topologies §2.3): suppress noise before expensive LLM
    # If price_delta < threshold, skip publishing to avoid Token Burn on minor signals.
    apply_wakeup_predicate = False  # Set True to demonstrate suppression; False preserves demo
    wakeup_threshold_pct = 0.5
    price_delta_pct = abs(tick.mid_price - quote_gen.initial_price) / quote_gen.initial_price * 100
    if apply_wakeup_predicate and price_delta_pct < wakeup_threshold_pct:
        log_with_dfid(
            logger, dfid, logging.INFO,
            "Wake-up predicate: price_delta=%.2f%% < %.1f%% - suppressed (no agents invoked)",
            price_delta_pct, wakeup_threshold_pct,
        )
    else:
        # Publish OBSERVATION (inversion of control: runtime emits, agents react)
        metadata = EventMetadata(dfid=dfid, target_scope=scope, context_snapshot_id=context_ref)
        bus.publish(
            EventType.OBSERVATION,
            observation_payload,
            metadata=metadata,
        )

    # 5. Unsubscribe and arbitrate
    bus.unsubscribe(EventType.POLICY_PROPOSAL, collect_proposal)
    bus.unsubscribe(EventType.OBSERVATION, risk_agent.on_observation)
    bus.unsubscribe(EventType.OBSERVATION, strategy_agent.on_observation)

    chosen = arbitrate_by_priority(proposals)

    retry_governor = IntentRetryGovernor(max_retries=3, db_path=None)
    if chosen:
        context = {"state": {"risk_score": context_snapshot.get("risk_score", 0.1)}}
        result, reason = validate_proposal(chosen, context, retry_governor=retry_governor)
        log_with_dfid(logger, dfid, logging.INFO, "DIM result=%s reason=%s", result, reason)
        # Lifecycle transition: reset IntentRetryGovernor on terminal state (DIR §4.3)
        if result == "ACCEPT":
            transition(dfid, FlowStatus.VALIDATING, FlowStatus.CLOSED, retry_governor=retry_governor)
            log_with_dfid(logger, dfid, logging.INFO, "Mock execution for %s (policy=%s)", chosen.agent_id, chosen.policy_kind)
        else:
            transition(dfid, FlowStatus.VALIDATING, FlowStatus.ABORTED, retry_governor=retry_governor)

    print(f"[SUMMARY] DFID={dfid} proposals={len(proposals)} chosen={chosen.agent_id if chosen else None} policy={chosen.policy_kind if chosen else None}")


if __name__ == "__main__":
    main()

