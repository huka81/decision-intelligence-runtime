"""Custom DIM validators for ``validate_proposal`` (Guide §3: ``dim.py``)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from dir_core import PolicyProposal, verify_drift


def fraud_hard_limit(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    _contract: Dict[str, Any],
) -> Optional[str]:
    limit = float(context.get("global_max_limit", 50_000.0))
    try:
        amt = float(proposal.params.get("amount", 0.0))
    except (TypeError, ValueError):
        return "HARD_LIMIT: invalid amount in proposal.params"
    if amt > limit:
        return f"HARD_LIMIT_EXCEEDED: amount {amt} > {limit}"
    return None


def fraud_state_drift(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    _contract: Dict[str, Any],
) -> Optional[str]:
    uid = proposal.params.get("user_id")
    if not isinstance(uid, str) or not uid:
        return "STATE_DRIFT: missing user_id in proposal.params"

    snap_all = context.get("snapshot_user") or {}
    live_all = context.get("live_risk") or {}
    snap = snap_all.get(uid)
    live = live_all.get(uid)
    if snap is None:
        return None
    if live is None:
        return f"STATE_DRIFT: missing live risk row for user {uid}"
    if not isinstance(snap, dict) or not isinstance(live, dict):
        return "STATE_DRIFT: snapshot or live state is not a dict"

    keys: List[str] = [k for k in snap if k in live]
    if not keys:
        return "STATE_DRIFT: no overlapping keys between snapshot and live state"

    snap_trim = {k: snap[k] for k in keys}
    live_trim = {k: live[k] for k in keys}
    ok, msg = verify_drift(snap_trim, live_trim, keys_to_compare=keys)
    if not ok:
        return msg
    return None


def dim_validators() -> List[
    Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]
]:
    """Use as ``custom_validators=dim_validators()`` in ``validate_proposal``."""
    return [fraud_hard_limit, fraud_state_drift]
