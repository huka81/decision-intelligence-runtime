"""Map the in-memory risk fake into the ``live_risk`` slice passed to DIM."""

from __future__ import annotations

from typing import Any, Dict

from .external_risk_store import InMemoryRiskStore


def live_risk_rows_from_store(
    store: InMemoryRiskStore,
    snapshot: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build ``user_id -> {status, risk_score}`` for users present in the YAML snapshot."""
    out: Dict[str, Dict[str, Any]] = {}
    for uid in snapshot:
        row = store.get(uid)
        if row:
            out[uid] = {"status": row["status"], "risk_score": row["risk_score"]}
    return out
