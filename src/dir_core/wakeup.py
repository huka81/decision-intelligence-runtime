"""
Wake-up Predicates (DIR Topologies §2.3) — Signal Suppression.

Low-cost heuristics evaluated BEFORE activating expensive LLM agents.
If any predicate returns False, the agent is not woken up (Token Burn prevention).
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


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
        logger.debug(
            "  Predicate '%s': %s", self.name, "PASS" if result else "SKIP"
        )
        return result


def price_change_significant(
    payload: Dict[str, Any], threshold: float = 0.005
) -> bool:
    """Wake up only if price change > threshold (0.5% default)."""
    delta = abs(payload.get("price_delta_pct", 0))
    return delta > threshold


def volatility_elevated(
    payload: Dict[str, Any], threshold: float = 0.03
) -> bool:
    """Wake up only if volatility is elevated."""
    return payload.get("volatility", 0) > threshold


def is_relevant_instrument(
    payload: Dict[str, Any], instruments: List[str]
) -> bool:
    """Wake up only for specific instruments."""
    return payload.get("instrument") in instruments


def should_wake(
    payload: Dict[str, Any], predicates: List[WakeupPredicate]
) -> bool:
    """Evaluate all wake-up predicates. All must pass for agent to wake."""
    for predicate in predicates:
        if not predicate.evaluate(payload):
            return False
    return True
