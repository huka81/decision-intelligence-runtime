"""DIM extras: CPC ceiling and Topology B JIT drift (snapshot vs live)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from dir_core import PolicyProposal, validate_proposal
from dir_core.data_types import ValidationResult
from dir_core.jit import verify_drift
from dir_core.models import ResponsibilityContract


def _jit_market_drift(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    contract: Dict[str, Any],
) -> Optional[str]:
    snap = context.get("market_snapshot")
    live = context.get("market_live")
    if not isinstance(snap, dict) or not isinstance(live, dict):
        return "Missing market_snapshot or market_live for JIT check"
    keys = ["market_cpc_to_win", "cycle_id"]
    ok, reason = verify_drift(snap, live, keys_to_compare=keys)
    if not ok:
        return reason
    return None


def _cpc_ceiling(max_cpc_usd: float) -> Callable[..., Optional[str]]:
    def _validator(
        proposal: PolicyProposal,
        context: Dict[str, Any],
        contract: Dict[str, Any],
    ) -> Optional[str]:
        raw = proposal.params.get("cpc_bid_usd")
        if raw is None:
            return "Missing cpc_bid_usd in params"
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            return "Invalid cpc_bid_usd type"
        if amount <= 0:
            return "Non-positive cpc_bid_usd"
        if amount > max_cpc_usd + 1e-9:
            return f"CPC_EXCEEDS_CONTRACT max={max_cpc_usd}"
        return None

    return _validator


def dim_validators(max_cpc_usd: float) -> List[Callable[..., Optional[str]]]:
    return [_jit_market_drift, _cpc_ceiling(max_cpc_usd)]


def validate_bidding_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]],
    rc: ResponsibilityContract,
) -> ValidationResult:
    contract_dict = rc.model_dump()
    return validate_proposal(
        proposal,
        context,
        allowed_agents=allowed_agents,
        contract=contract_dict,
        custom_validators=dim_validators(float(rc.max_drawdown_limit)),
    )
