"""
EOAM orchestrator: register agents, emit observation/news, collect proposals,
arbitrate by priority, DIM (called by run.py), spawn PositionAgents on OPEN_POSITION.

DIR Topologies §2: Event-Oriented Agent Mesh.
"""  # noqa: E501

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from dir_core import (
    EventBus,
    EventMetadata,
    EventType,
    PolicyProposal,
    new_dfid,
    select_winner,
)
from dir_core.utils.logging_utils import log_with_dfid
from contracts import FinanceContract

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dir_kernel_wiring import SimulationKernelContext


class ObservationAgent(Protocol):
    """Protocol for agents that react to OBSERVATION and optionally NEWS."""

    @property
    def scope(self) -> Optional[str]: ...
    @property
    def agent_id(self) -> str: ...

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]: ...
    def on_news(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]: ...  # noqa: E501


@dataclass
class EOAMOrchestrator:
    """
    Orchestrates EOAM: register agents, emit observation/news, collect proposals,
    arbitrate by priority_matrix (policy_kind -> priority), spawn position agents.
    DIM validation is done by the caller (run.py).
    
    Implements Wake-up Predicates (DIR Topologies §2.3) for Signal Suppression.
    """  # noqa: E501

    bus: EventBus
    priority_matrix: Dict[str, int] = field(default_factory=dict)
    _pending: Dict[str, List[PolicyProposal]] = field(default_factory=dict)
    _position_agents: List[Any] = field(default_factory=list)
    _instrument_agents: Dict[str, Any] = field(default_factory=dict)
    _agent_handlers: Dict[str, Any] = field(default_factory=dict)  # agent_id -> handler for unsubscribe
    _next_position_id: int = 1
    _llm: Optional[Any] = field(default=None)
    _position_template: Optional[Dict[str, Any]] = field(default=None)
    # Wake-up Predicates: Track last prices for signal suppression (DIR Topologies §2.3)
    _last_prices: Dict[str, float] = field(default_factory=dict)  # scope -> last_price
    _suppressed_signals: int = field(default=0)  # Counter for logging
    _kernel_ctx: Optional[Any] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.priority_matrix:
            self.priority_matrix = {
                "RISK_ALERT": 1,
                "CLOSE": 2,
                "TAKE_PROFIT": 3,
                "ADJUST_STOP": 4,
                "OPEN_POSITION": 5,
                "NEWS_QUALIFIED": 6,
                "HOLD": 10,
            }

    def set_spawn_deps(
        self, llm: Any, position_template: Dict[str, Any]
    ) -> None:
        """Set LLM and position template for spawning ROA PositionAgents."""
        self._llm = llm
        self._position_template = position_template

    def set_kernel_context(self, kernel_ctx: Optional["SimulationKernelContext"]) -> None:
        """Optional DIR bundle wiring for spawned agents (Context Store persistence)."""
        self._kernel_ctx = kernel_ctx

    def register_agent(self, agent: ObservationAgent) -> None:
        """Subscribe agent to OBSERVATION (scope-based) with Wake-up Predicates (DIR Topologies §2.3).
        
        Implements Signal Suppression: Only invoke agent if price change exceeds
        wake_up_threshold_pct to prevent "Token Burn" on minor signals.
        """

        def handler(payload: Dict[str, Any]) -> None:
            # Wake-up Predicate: Check if price delta exceeds threshold (DIR Topologies §2.3)
            scope = agent.scope
            current_price = payload.get("price")
            
            # Get wake_up_threshold_pct from agent's contract (default 0.5%)
            wake_up_threshold_pct = 0.5  # Default
            if hasattr(agent, "contract") and hasattr(agent.contract, "wake_up_threshold_pct"):
                wake_up_threshold_pct = agent.contract.wake_up_threshold_pct
            
            # Check if signal should be suppressed
            if scope and current_price is not None:
                last_price = self._last_prices.get(scope)
                
                if last_price is not None:
                    price_change_pct = abs((current_price - last_price) / last_price * 100)
                    
                    if price_change_pct < wake_up_threshold_pct:
                        # Signal suppressed - price change too small
                        self._suppressed_signals += 1
                        dfid = payload.get("dfid", "unknown")
                        if self._suppressed_signals % 10 == 1:  # Log every 10th suppression
                            log_with_dfid(
                                logger, dfid, logging.DEBUG,
                                "Wake-up Predicate: Signal SUPPRESSED for %s (Δ%.3f%% < %.1f%% threshold) [%d total]",
                                agent.agent_id, price_change_pct, wake_up_threshold_pct, self._suppressed_signals,
                            )
                        return  # Suppress signal - don't invoke agent
                    else:
                        # Signal passes - log activation
                        dfid = payload.get("dfid", "unknown")
                        log_with_dfid(
                            logger, dfid, logging.DEBUG,
                            "Wake-up Predicate: Agent %s ACTIVATED (Δ%.3f%% >= %.1f%%)",
                            agent.agent_id, price_change_pct, wake_up_threshold_pct,
                        )
                
                # Update last price for this scope
                self._last_prices[scope] = current_price
            
            # Invoke agent (signal not suppressed or first observation)
            prop = agent.on_observation(payload)
            if prop:
                dfid = payload.get("dfid", "unknown")
                if dfid not in self._pending:
                    self._pending[dfid] = []
                self._pending[dfid].append(prop)

        self.bus.subscribe(EventType.OBSERVATION, handler, scope=agent.scope)
        # Store handler for later unsubscription
        self._agent_handlers[agent.agent_id] = handler
        # Position agents (have position_id) go to _position_agents
        # Instrument agents (have instrument but NO position_id) go to _instrument_agents
        if hasattr(agent, "position_id"):
            self._position_agents.append(agent)
        elif hasattr(agent, "instrument"):
            self._instrument_agents[agent.instrument] = agent

    def register_news_agent(self, agent: ObservationAgent) -> None:
        """Subscribe agent to NEWS."""

        def handler(payload: Dict[str, Any]) -> None:
            prop = agent.on_news(payload)
            if prop:
                dfid = payload.get("dfid", "unknown")
                if dfid not in self._pending:
                    self._pending[dfid] = []
                self._pending[dfid].append(prop)

        self.bus.subscribe(EventType.NEWS, handler, scope=None)

    def emit_observation(self, payload: Dict[str, Any], scope: Optional[str] = None) -> str:
        dfid = payload.get("dfid") or new_dfid()
        payload["dfid"] = dfid
        self.bus.publish(
            EventType.OBSERVATION,
            payload,
            EventMetadata(dfid=dfid, target_scope=scope, source_agent="orchestrator"),
        )
        return dfid

    def emit_news(self, payload: Dict[str, Any]) -> str:
        dfid = payload.get("dfid") or new_dfid()
        payload["dfid"] = dfid
        self.bus.publish(
            EventType.NEWS,
            payload,
            EventMetadata(dfid=dfid, source_agent="news_generator"),
        )
        return dfid

    def arbitrate(self, dfid: str) -> Optional[PolicyProposal]:
        proposals = self._pending.get(dfid, [])
        winner = select_winner(proposals, self.priority_matrix)
        if winner:
            log_with_dfid(
                logger, dfid, logging.INFO,
                "Arbitration: %d proposals → winner %s from %s",
                len(proposals), winner.policy_kind, winner.agent_id,
            )
        return winner

    def clear_pending(self, dfid: str) -> None:
        self._pending.pop(dfid, None)

    def spawn_position_agent(
        self,
        instrument: str,
        entry_price: float,
        initial_exposure: float,
        quantity: float,
        parent_dfid: Optional[str] = None,
        parent_agent_id: Optional[str] = None,
        news_headline: Optional[str] = None,
    ) -> Any:
        """Create and register a new ROA PositionAgent with exposure tracking.

        When spawned from NEWS_QUALIFIED, parent_dfid links to the news event DFID for
        hierarchical DFID correlation.
        
        Args:
            instrument: Trading instrument (e.g., "BTC-USD")
            entry_price: Entry price at spawn time
            initial_exposure: USD capital allocated to this position
            quantity: Number of units/coins (initial_exposure / entry_price)
            parent_dfid: Parent news event DFID
            parent_agent_id: Parent agent ID (typically "news_scorer")
            news_headline: News headline that triggered spawn
        
        Returns:
            Spawned ROAPositionAgent instance
        """
        if not self._llm or not self._position_template:
            raise RuntimeError(
                "Orchestrator.set_spawn_deps(llm, position_template) must be called before spawn"
            )
        try:
            from .roa_agents import ROAPositionAgent
        except ImportError:
            from roa_agents import ROAPositionAgent

        position_id = f"POS_{self._next_position_id}"
        self._next_position_id += 1
        t = self._position_template
        raw_contract = dict(t.get("contract", {}))
        contract_data = dict(raw_contract)
        subject = dict(contract_data.get("subject") or {})
        subject["agent_id"] = f"position_{position_id}"
        subject["parent_agent_id"] = parent_agent_id or subject.get("parent_agent_id")
        authority = dict(contract_data.get("authority") or {})
        scope = dict(authority.get("resource_scope") or {})
        scope["instruments"] = [instrument]
        authority["resource_scope"] = scope
        contract_data["subject"] = subject
        contract_data["authority"] = authority
        contract_data["mission"] = t.get("mission") or contract_data.get("mission", "")
        contract = FinanceContract.from_raw(contract_data)
        agent = ROAPositionAgent(
            contract=contract,
            llm=self._llm,
            position_id=position_id,
            instrument=instrument,
            entry_price=entry_price,
            initial_exposure=initial_exposure,
            quantity=quantity,
            kernel_ctx=self._kernel_ctx,
        )
        if parent_dfid:
            setattr(agent, "_parent_dfid", parent_dfid)
        if news_headline:
            setattr(agent, "_news_headline", news_headline)
        self.register_agent(agent)
        log_with_dfid(
            logger, "", logging.INFO,
            "Spawned %s for %s @ $%.2f, exposure=$%.2f, quantity=%.6f (parent_dfid=%s)",
            agent.agent_id, instrument, entry_price, initial_exposure, quantity, parent_dfid or "—",
        )
        return agent
    
    def cleanup_position_agent(self, agent_id: str) -> None:
        """Unsubscribe and remove a position agent (on CLOSE).
        
        Args:
            agent_id: Agent ID to cleanup (e.g., "position_POS_1")
        """
        # Find agent in _position_agents
        agent = None
        for a in self._position_agents:
            if a.agent_id == agent_id:
                agent = a
                break
        
        if not agent:
            logger.warning("Agent %s not found in position_agents for cleanup", agent_id)
            return
        
        # Unsubscribe from event bus
        handler = self._agent_handlers.pop(agent_id, None)
        if handler:
            self.bus.unsubscribe(EventType.OBSERVATION, handler)
        
        # Remove from tracking list
        self._position_agents = [a for a in self._position_agents if a.agent_id != agent_id]
        
        log_with_dfid(
            logger, "", logging.INFO,
            "Cleaned up %s: unsubscribed from %s events, removed from registry",
            agent_id, agent.instrument,
        )
    
    def get_signal_suppression_stats(self) -> Dict[str, Any]:
        """Get Wake-up Predicates statistics (DIR Topologies §2.3).
        
        Returns:
            Dictionary with signal suppression metrics
        """
        return {
            "suppressed_signals": self._suppressed_signals,
            "tracked_instruments": list(self._last_prices.keys()),
            "last_prices": dict(self._last_prices),
        }

