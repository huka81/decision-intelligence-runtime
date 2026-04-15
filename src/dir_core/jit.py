"""
Just-In-Time (JIT) State Verification (DIR §6.5, Topologies §2.4, §3.2).

Fast-pass checks before execution: verify state has not drifted since snapshot.
Does NOT re-evaluate reasoning — only compares snapshot vs live state.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .data_types import ValidationResult, ValidationVerdict

logger = logging.getLogger(__name__)


def verify_drift(
    snapshot: Dict[str, Any],
    live: Dict[str, Any],
    keys_to_compare: Optional[List[str]] = None,
    tolerance: Optional[Dict[str, float]] = None,
) -> Tuple[bool, str]:
    """
    Verify that live state has not drifted beyond tolerance since snapshot.

    Args:
        snapshot: State at snapshot time (when agent reasoned).
        live: Current live state.
        keys_to_compare: Keys to check. If None, compare all keys in snapshot.
        tolerance: Optional dict of key -> max allowed delta for numeric values.
            If key not in tolerance, exact match is required.

    Returns:
        (True, "") if no drift, else (False, reason).
    """
    tolerance = tolerance or {}
    keys = keys_to_compare or list(snapshot.keys())

    for key in keys:
        snap_val = snapshot.get(key)
        live_val = live.get(key)

        if key in tolerance:
            try:
                snap_num = float(snap_val) if snap_val is not None else 0.0
                live_num = float(live_val) if live_val is not None else 0.0
                if abs(snap_num - live_num) > tolerance[key]:
                    return (
                        False,
                        f"STATE_DRIFT: {key} changed beyond tolerance "
                        f"(snapshot={snap_val}, live={live_val})",
                    )
            except (TypeError, ValueError):
                if snap_val != live_val:
                    return (
                        False,
                        f"STATE_DRIFT: {key} mismatch (snapshot={snap_val}, live={live_val})",
                    )
        else:
            if snap_val != live_val:
                return (
                    False,
                    f"STATE_DRIFT: {key} changed (snapshot={snap_val}, live={live_val})",
                )

    return True, ""


class JITStateVerifier:
    """
    JIT State Verifier for Topology B (SDS).

    Validates that the environment has not drifted since the agent's snapshot.
    Domain-specific logic (which keys, hard limits) is passed via callbacks.
    """

    def verify(
        self,
        snapshot: Dict[str, Any],
        live: Dict[str, Any],
        keys_to_compare: Optional[List[str]] = None,
        tolerance: Optional[Dict[str, float]] = None,
    ) -> ValidationResult:
        """
        Run drift verification.

        Returns:
            ("ACCEPT", reason) if no drift, else ("REJECT", reason).
        """
        ok, reason = verify_drift(
            snapshot, live,
            keys_to_compare=keys_to_compare,
            tolerance=tolerance,
        )
        if ok:
            return ValidationVerdict.ACCEPT, "no state drift"
        return ValidationVerdict.REJECT, reason
