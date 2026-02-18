"""
EOAM orchestrator: register agents, emit observation/news, collect proposals,
arbitrate by priority, DIM (called by run.py), spawn PositionAgents on OPEN_POSITION.

DIR Topologies §2: Event-Oriented Agent Mesh.
"""  # noqa: E501

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from dir_runtime import EventBus, EventMetadata, EventType, PolicyProposal, new_dfid
from dir_runtime.logging_utils import log_with_dfid

logger = logging.getLogger(__name__)


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
    """  # noqa: E501

    bus: EventBus
    priority_matrix: Dict[str, int] = field(default_factory=dict)
    _pending: Dict[str, List[PolicyProposal]] = field(default_factory=dict)
    _position_agents: List[Any] = field(default_factory=list)
    _instrument_agents: Dict[str, Any] = field(default_factory=dict)
    _next_position_id: int = 1
    _llm: Optional[Any] = field(default=None)
    _position_template: Optional[Dict[str, Any]] = field(default=None)

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

    def register_agent(self, agent: ObservationAgent) -> None:
        """Subscribe agent to OBSERVATION (scope-based)."""

        def handler(payload: Dict[str, Any]) -> None:
            prop = agent.on_observation(payload)
            if prop:
                dfid = payload.get("dfid", "unknown")
                if dfid not in self._pending:
                    self._pending[dfid] = []
                self._pending[dfid].append(prop)

        self.bus.subscribe(EventType.OBSERVATION, handler, scope=agent.scope)
        if hasattr(agent, "instrument"):
            self._instrument_agents[agent.instrument] = agent
        elif hasattr(agent, "position_id"):
            self._position_agents.append(agent)

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
        if not proposals:
            return None

        def prio(p: PolicyProposal) -> int:
            return self.priority_matrix.get(p.policy_kind, 10)

        winner = min(proposals, key=prio)
        log_with_dfid(
            logger, dfid, logging.INFO,
            "Arbitration: %d proposals → winner %s from %s",
            len(proposals), winner.policy_kind, winner.agent_id,
        )  # noqa: E501
        return winner

    def clear_pending(self, dfid: str) -> None:
        self._pending.pop(dfid, None)

    def spawn_position_agent(self, instrument: str, entry_price: float) -> Any:
        """Create and register a new ROA PositionAgent from config template."""
        if not self._llm or not self._position_template:
            raise RuntimeError(
                "Orchestrator.set_spawn_deps(llm, position_template) must be called before spawn"
            )
        from dir_runtime import ResponsibilityContract
        try:
            from .roa_agents import ROAPositionAgent
        except ImportError:
            from roa_agents import ROAPositionAgent

        position_id = f"POS_{self._next_position_id}"
        self._next_position_id += 1
        t = self._position_template
        contract_dict = dict(t.get("contract", {}))
        contract_dict["agent_id"] = f"position_{position_id}"
        contract_dict["authorized_instruments"] = [instrument]
        contract_dict["parent_agent_id"] = contract_dict.get("parent_agent_id")
        contract_dict["mission"] = t.get("mission", "")
        contract = ResponsibilityContract(**contract_dict)
        agent = ROAPositionAgent(
            contract=contract,
            llm=self._llm,
            position_id=position_id,
            instrument=instrument,
            entry_price=entry_price,
        )
        self.register_agent(agent)
        log_with_dfid(
            logger, "", logging.INFO,
            "Spawned %s for %s at %.2f",
            agent.agent_id, instrument, entry_price,
        )
        return agent
