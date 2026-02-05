#!/usr/bin/env python3
"""
09_topology_a_eoam - Topology A: Event bus, parallel agents, DIM, mock execution.
Run from repo root: python samples/09_topology_a_eoam/run.py
Requires PYTHONPATH including workspace src/ (see .vscode/settings.json).
"""
import logging

from dir import EventBus, EventType, new_dfid, PolicyProposal
from dir.dim import validate
from dir.logging_utils import log_with_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    dfid = new_dfid()
    log_with_dfid(logger, dfid, logging.INFO, "EOAM: Observation received")

    bus = EventBus()
    proposals: list[PolicyProposal] = []

    def collect_proposal(payload: dict) -> None:
        p = payload.get("proposal")
        if p is not None:
            proposals.append(p)

    bus.subscribe(EventType.POLICY_PROPOSAL, collect_proposal)
    # Simulate two agents reacting to same observation
    for i, agent_id in enumerate(["agent_risk", "agent_strategy"]):
        prop = PolicyProposal(
            dfid=dfid,
            agent_id=agent_id,
            policy_kind="ADJUST",
            params={"priority": i, "action": "HOLD"},
        )
        bus.publish(EventType.POLICY_PROPOSAL, {"proposal": prop})
    bus.unsubscribe(EventType.POLICY_PROPOSAL, collect_proposal)

    # Arbitrate: take first (or by priority)
    chosen = proposals[0] if proposals else None
    if chosen:
        result, reason = validate(chosen)
        log_with_dfid(logger, dfid, logging.INFO, "DIM result=%s reason=%s", result, reason)
        log_with_dfid(logger, dfid, logging.INFO, "Mock execution for %s", chosen.agent_id)

    print(f"[SUMMARY] DFID={dfid} proposals={len(proposals)} chosen={chosen.agent_id if chosen else None}")


if __name__ == "__main__":
    main()
