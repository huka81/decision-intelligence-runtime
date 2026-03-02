"""
JITValidator - Fast-Pass checks for SDS (Topology B).

DIR §6.5 / Topologies §3.2: Just-In-Time State Re-verification.
Does NOT re-evaluate reasoning (too slow). Checks:
1. State Drift: Has the user's risk score/status changed since the snapshot?
2. Hard Limits: Is amount > Global_Max_Limit?
3. Schema sanity: DecisionAtom is valid (defense-in-depth).
"""

import logging
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import ValidationError

try:
    from .risk_cache import RiskCache
    from .schemas import DecisionAtom
except ImportError:
    from risk_cache import RiskCache
    from schemas import DecisionAtom

logger = logging.getLogger(__name__)

ValidationVerdict = Literal["ACCEPT", "REJECT"]
ValidationResult = Tuple[ValidationVerdict, str]

# Default hard limit (overridden by config.yaml)
DEFAULT_GLOBAL_MAX_LIMIT = 50_000.0


def validate(
    atom: DecisionAtom,
    risk_cache: RiskCache,
    snapshot_user_state: Optional[Dict[str, Dict[str, Any]]] = None,
    global_max_limit: Optional[float] = None,
) -> ValidationResult:
    """
    Fast-Pass JIT validation.

    Args:
        atom: The DecisionAtom from the agent.
        risk_cache: Current risk state (live).
        snapshot_user_state: State at snapshot time, keyed by user_id.
            e.g. {"user_123": {"status": "clean", "risk_score": 0.1}}
        global_max_limit: Hard limit for amount (from config). Default: 50_000.
    """
    limit = global_max_limit if global_max_limit is not None else DEFAULT_GLOBAL_MAX_LIMIT

    # 1. Schema sanity (defense-in-depth)
    try:
        # Re-validate as DecisionAtom
        DecisionAtom.model_validate(atom.model_dump())
    except ValidationError as e:
        return "REJECT", f"SCHEMA_ERROR: {e}"

    # 2. Hard Limits
    if atom.amount > limit:
        return "REJECT", f"HARD_LIMIT_EXCEEDED: amount {atom.amount} > {limit}"

    # 3. State Drift
    current = risk_cache.get(atom.user_id)
    snapshot = (snapshot_user_state or {}).get(atom.user_id)

    if snapshot is not None and current is not None:
        snapshot_status = snapshot.get("status", "unknown")
        current_status = current.get("status", "unknown")
        if current_status != snapshot_status:
            reason = (
                f"STATE_DRIFT_ERROR: user {atom.user_id} was '{snapshot_status}' "
                f"in snapshot, now '{current_status}' (Runtime detected change)"
            )
            return "REJECT", reason

    reasons = ["schema OK", f"amount<=${limit:,.0f}", "no state drift"]
    return "ACCEPT", ", ".join(reasons)
