"""Custom DIM validators for credit-limit hard gates."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from dir_core import PolicyProposal


def credit_max_limit(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    _contract: Dict[str, Any],
) -> Optional[str]:
    limit = float(context.get("max_limit_pln", 10_000.0))
    try:
        requested = float(proposal.params.get("requested_limit_pln", 0.0))
    except (TypeError, ValueError):
        return "HARD_LIMIT: invalid requested_limit_pln in proposal.params"
    if requested > limit:
        return f"HARD_LIMIT_EXCEEDED: requested {requested} > max {limit}"
    return None


def dim_validators() -> List[
    Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]
]:
    return [credit_max_limit]
