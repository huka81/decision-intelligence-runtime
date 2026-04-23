#!/usr/bin/env python3
"""
09_topology_a_eoam — Technical minimal demo: Topology A (EOAM).

Focus: create_event_bus, OBSERVATION with scope, parallel reactive agents,
priority_matrix arbitration, DecisionRuntime handshake, DIM (default in-memory audit).

Aligned with ``.cursor/rules/06-technical-sample-development-guide.mdc`` — no shared
bootstrap, no YAML config.

Run from repo root: python samples/09_topology_a_eoam/run.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLE_DIR = Path(__file__).resolve().parent
for _p in (_SRC, _SAMPLE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core import (
    DecisionRuntime,
    EventBus,
    EventMetadata,
    EventType,
    PolicyProposal,
    ResponsibilityContract,
    create_event_bus,
    new_dfid,
)
from dir_core.data_types import ContractRole, ValidationVerdict
from dir_core.intent_retry import IntentRetryGovernor
from dir_core.lifecycle import FlowStatus, transition
from dir_core.storage import memory_storage
from dir_core.utils.logging_utils import log_with_dfid

from mocks import QuoteGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- Inline demo parameters (no config.yaml) ---------------------------------
_PRIORITY_MATRIX: Dict[str, int] = {"ALERT": 1, "ADJUST": 2, "HOLD": 10}
_INSTRUMENT = "BTC-USD"
_QUOTE_SEED = 42
_INITIAL_PRICE = 50_000.0
_QUOTE_VOLATILITY = 0.03
_RISK_VOL_ALERT_ABOVE = 0.025
_APPLY_WAKE_UP = False
_WAKE_UP_THRESHOLD_PCT = 0.5
_EVENT_BUS_WITH_LOGGING = False


def _priority_rank(policy_kind: str, default: int = 99) -> int:
    return int(_PRIORITY_MATRIX.get(policy_kind, default))


def _arbitrate(proposals: List[PolicyProposal]) -> Optional[PolicyProposal]:
    if not proposals:
        return None
    return min(proposals, key=lambda p: _priority_rank(p.policy_kind))


class RiskAgent:
    """OBSERVATION subscriber; ALERT or HOLD from a volatility heuristic."""

    def __init__(
        self,
        bus: EventBus,
        agent_id: str,
        scope: str,
        volatility_alert_above: float,
    ) -> None:
        self.bus = bus
        self.agent_id = agent_id
        self.scope = scope
        self.volatility_alert_above = volatility_alert_above
        bus.subscribe(EventType.OBSERVATION, self.on_observation, scope=scope)

    def on_observation(self, payload: Dict[str, Any]) -> None:
        dfid = str(payload.get("dfid", ""))
        context_ref = str(payload.get("context_ref", ""))
        volatility = float(payload.get("volatility", 0.0))
        instrument = str(payload.get("instrument", ""))
        above = self.volatility_alert_above
        policy_kind = "ALERT" if volatility > above else "HOLD"
        justification = f"Risk heuristic: volatility={volatility} threshold={above}"
        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy_kind,
            params={"instrument": instrument, "volatility": volatility},
            context_ref=context_ref or None,
            confidence=1.0,
            justification=justification,
        )
        self.bus.publish(EventType.POLICY_PROPOSAL, {"proposal": proposal})
        log_with_dfid(
            logger, dfid, logging.DEBUG, "%s proposed %s", self.agent_id, policy_kind
        )


class StrategyAgent:
    """OBSERVATION subscriber; ADJUST on bullish trend, else HOLD."""

    def __init__(self, bus: EventBus, agent_id: str, scope: str) -> None:
        self.bus = bus
        self.agent_id = agent_id
        self.scope = scope
        bus.subscribe(EventType.OBSERVATION, self.on_observation, scope=scope)

    def on_observation(self, payload: Dict[str, Any]) -> None:
        dfid = str(payload.get("dfid", ""))
        context_ref = str(payload.get("context_ref", ""))
        trend = str(payload.get("trend", "neutral"))
        instrument = str(payload.get("instrument", ""))
        policy_kind = "ADJUST" if trend == "bullish" else "HOLD"
        justification = f"Strategy heuristic: trend={trend}"
        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=policy_kind,
            params={"instrument": instrument, "trend": trend},
            context_ref=context_ref or None,
            confidence=1.0,
            justification=justification,
        )
        self.bus.publish(EventType.POLICY_PROPOSAL, {"proposal": proposal})
        log_with_dfid(
            logger, dfid, logging.DEBUG, "%s proposed %s", self.agent_id, policy_kind
        )


def _contracts() -> Dict[str, Dict[str, Any]]:
    return {
        "agent_risk": ResponsibilityContract(
            agent_id="agent_risk",
            role=ContractRole.MONITOR,
            mission="React to observations; ALERT when volatility is elevated.",
            authorized_instruments=[_INSTRUMENT],
            allowed_policy_types=["ALERT", "HOLD"],
            escalate_on_uncertainty=0.7,
            max_drawdown_limit=0.05,
            wake_up_threshold_pct=0.5,
            parent_agent_id=None,
        ).model_dump(),
        "agent_strategy": ResponsibilityContract(
            agent_id="agent_strategy",
            role=ContractRole.STRATEGIST,
            mission="React to observations; ADJUST on bullish trend, else HOLD.",
            authorized_instruments=[_INSTRUMENT],
            allowed_policy_types=["ADJUST", "HOLD"],
            escalate_on_uncertainty=0.7,
            max_drawdown_limit=0.05,
            wake_up_threshold_pct=0.5,
            parent_agent_id=None,
        ).model_dump(),
    }


def main() -> None:
    bundle = memory_storage()
    runtime = DecisionRuntime(bundle)
    contracts = _contracts()

    for agent_id, cdict in contracts.items():
        hr = runtime.register_agent(
            agent_id,
            cdict,
            agent_version="1.0.0",
            priority=5 if agent_id == "agent_risk" else 8,
        )
        if not hr.accepted:
            logger.error("Handshake rejected for %s: %s", agent_id, hr.reason)
            return

    dfid = new_dfid()
    bus: EventBus = create_event_bus(
        backend="memory",
        with_logging=_EVENT_BUS_WITH_LOGGING,
    )
    proposals: List[PolicyProposal] = []

    def collect_proposal(payload: dict) -> None:
        p = payload.get("proposal")
        if isinstance(p, PolicyProposal):
            proposals.append(p)

    risk = RiskAgent(bus, "agent_risk", _INSTRUMENT, _RISK_VOL_ALERT_ABOVE)
    strategy = StrategyAgent(bus, "agent_strategy", _INSTRUMENT)
    bus.subscribe(EventType.POLICY_PROPOSAL, collect_proposal)

    quote_gen = QuoteGenerator(
        instrument=_INSTRUMENT,
        initial_price=_INITIAL_PRICE,
        volatility=_QUOTE_VOLATILITY,
        seed=_QUOTE_SEED,
    )
    tick = quote_gen.next_tick()
    observation_payload: Dict[str, Any] = tick.to_payload()
    context_snapshot: Dict[str, Any] = {
        "instrument": _INSTRUMENT,
        "price": observation_payload.get("price"),
        "volatility": observation_payload.get("volatility", 0),
        "risk_score": 0.1,
    }
    context_ref = f"ctx_{dfid[:8]}"
    observation_payload["dfid"] = dfid
    observation_payload["context_ref"] = context_ref

    log_with_dfid(logger, dfid, logging.INFO, "EOAM: publishing OBSERVATION for %s", _INSTRUMENT)

    price_delta_pct = (
        abs(tick.mid_price - quote_gen.initial_price) / quote_gen.initial_price * 100
        if quote_gen.initial_price
        else 0.0
    )
    if _APPLY_WAKE_UP and price_delta_pct < _WAKE_UP_THRESHOLD_PCT:
        log_with_dfid(
            logger,
            dfid,
            logging.INFO,
            "Wake-up predicate: |price_delta|=%.4f%% < %.2f%% — suppressed",
            price_delta_pct,
            _WAKE_UP_THRESHOLD_PCT,
        )
        bus.unsubscribe(EventType.POLICY_PROPOSAL, collect_proposal)
        bus.unsubscribe(EventType.OBSERVATION, risk.on_observation)
        bus.unsubscribe(EventType.OBSERVATION, strategy.on_observation)
        log_with_dfid(
            logger,
            dfid,
            logging.INFO,
            "SUMMARY proposals=0 chosen=None verdict=None executed=False (wake-up)",
        )
        print(f"\n[SUMMARY] DFID={dfid} proposals=0 chosen=None verdict=None executed=False")
        return

    metadata = EventMetadata(
        dfid=dfid,
        target_scope=_INSTRUMENT,
        context_snapshot_id=context_ref,
    )
    bus.publish(EventType.OBSERVATION, observation_payload, metadata=metadata)

    bus.unsubscribe(EventType.POLICY_PROPOSAL, collect_proposal)
    bus.unsubscribe(EventType.OBSERVATION, risk.on_observation)
    bus.unsubscribe(EventType.OBSERVATION, strategy.on_observation)

    chosen = _arbitrate(proposals)
    retry_governor = IntentRetryGovernor(max_retries=3)
    verdict: Optional[ValidationVerdict] = None
    reason: Optional[str] = None
    executed = False

    if chosen is not None:
        dim_ctx = {"state": {"risk_score": context_snapshot.get("risk_score", 0.1)}}
        verdict, reason = runtime.evaluate_proposal(
            chosen,
            {},
            dim_context=dim_ctx,
            allowed_agents=[chosen.agent_id],
            retry_governor=retry_governor,
        )
        log_with_dfid(logger, dfid, logging.INFO, "DIM verdict=%s reason=%s", verdict, reason)
        if verdict == ValidationVerdict.ACCEPT:
            transition(
                dfid, FlowStatus.VALIDATING, FlowStatus.CLOSED, retry_governor=retry_governor
            )
            log_with_dfid(
                logger,
                dfid,
                logging.INFO,
                "Mock execution for %s policy=%s",
                chosen.agent_id,
                chosen.policy_kind,
            )
            executed = True
        else:
            transition(
                dfid, FlowStatus.VALIDATING, FlowStatus.ABORTED, retry_governor=retry_governor
            )

    n = len(proposals)
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "SUMMARY proposals=%d chosen_agent=%s chosen_policy=%s verdict=%s executed=%s",
        n,
        getattr(chosen, "agent_id", None),
        getattr(chosen, "policy_kind", None),
        str(verdict) if verdict is not None else None,
        executed,
    )
    print(
        f"\n[SUMMARY] DFID={dfid} proposals={n} "
        f"chosen={getattr(chosen, 'agent_id', None)} "
        f"policy={getattr(chosen, 'policy_kind', None)} "
        f"verdict={verdict} executed={executed}",
    )


if __name__ == "__main__":
    main()
