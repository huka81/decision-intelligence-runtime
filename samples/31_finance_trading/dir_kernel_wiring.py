"""
DIR kernel persistence for sample 31_finance_trading (DIR-minified §2.3, §3.2, §8).

Wires the canonical :class:`dir_core.storage.StorageBundle` to:

- **Agent Registry** — handshake for configured agents and spawned position agents
- **Context Store** — session (per DFID) ROA internal steps; state (per agent_id) last outcome
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dir_core import AgentRegistry, ContextStore, ResponsibilityContract
from dir_core.models import DecisionRecord

from shared.contracts.provider import ContractProvider

logger = logging.getLogger(__name__)

# SemVer passed to AgentRegistry.handshake (contracts from YAML have no embedded version).
AGENT_CONTRACT_VERSION = "1.0.0"


@dataclass
class SimulationKernelContext:
    """Filled before the tick loop: ``context_store`` early; ``simulation_id`` after audit start."""

    simulation_id: str = ""
    context_store: Optional[ContextStore] = None


def register_config_agents(
    registry: AgentRegistry,
    contracts: ContractProvider,
    agent_configs: List[Dict[str, Any]],
) -> None:
    """Handshake all agents from config except the ``position`` template row."""
    for cfg in agent_configs:
        agent_id = cfg.get("agent_id")
        if not agent_id or cfg.get("type") == "position":
            continue
        contract: ResponsibilityContract = contracts.get_contract(agent_id)
        priority = int(cfg.get("priority", 0))
        result = registry.handshake(
            agent_id,
            contract.model_dump(mode="json"),
            AGENT_CONTRACT_VERSION,
            priority=priority,
        )
        if not result.accepted:
            raise RuntimeError(
                f"AgentRegistry handshake rejected for {agent_id}: {result.reason}"
            )
        logger.info(
            "AgentRegistry: handshake OK for %s (priority=%s)", agent_id, priority
        )


def register_spawned_position_agent(registry: AgentRegistry, contract: ResponsibilityContract) -> None:
    """Persist a dynamically spawned position agent (same bundle as static agents)."""
    priority = 4
    result = registry.handshake(
        contract.agent_id,
        contract.model_dump(mode="json"),
        AGENT_CONTRACT_VERSION,
        priority=priority,
    )
    if not result.accepted:
        raise RuntimeError(
            f"AgentRegistry handshake rejected for position agent {contract.agent_id}: "
            f"{result.reason}"
        )
    logger.info("AgentRegistry: position agent %s registered", contract.agent_id)


def persist_roa_cycle_record(
    kernel_ctx: Optional[SimulationKernelContext],
    dfid: str,
    agent_id: str,
    record: DecisionRecord,
) -> None:
    """Append Explain→Policy outcome to Context Store (session + agent state)."""
    if kernel_ctx is None or not kernel_ctx.simulation_id:
        return
    cs = kernel_ctx.context_store
    if cs is None:
        return
    step = record.model_dump(mode="json")
    step["agent_id"] = agent_id
    step["simulation_id"] = kernel_ctx.simulation_id
    sess = cs.get_session(dfid)
    steps = list(sess.get("roa_internal_steps", []))
    steps.append(step)
    cs.update_session(
        dfid,
        {
            "roa_internal_steps": steps,
            "simulation_id": kernel_ctx.simulation_id,
        },
    )
    cs.update_state(
        agent_id,
        {
            "simulation_id": kernel_ctx.simulation_id,
            "last_dfid": dfid,
            "last_policy_action": record.policy_action,
            "last_outcome": str(record.outcome),
        },
    )
