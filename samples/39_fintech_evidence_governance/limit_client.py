"""
Mock credit-limit raise API (Kernel Space execution step).

Idempotency: SHA256(DFID + Step_ID + canonical params) per DIR-minified.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict

from dir_core.storage import AuditStore

logger = logging.getLogger(__name__)

RAISE_STEP_ID = "RAISE_CREDIT_LIMIT"
_seen_keys: set[str] = set()


def _canonical_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def compute_raise_idempotency_key(
    dfid: str, step_id: str, params: dict[str, Any]
) -> str:
    payload = f"{dfid}:{step_id}:{_canonical_params(params)}"
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class RaiseResult:
    ok: bool
    new_limit_pln: float
    idempotency_key: str
    cached: bool
    message: str


class CreditLimitClient:
    """Deterministic mock limit raise — no network."""

    def __init__(self, audit: AuditStore) -> None:
        self._audit = audit

    def raise_limit(
        self,
        dfid: str,
        *,
        simulation_id: str,
        customer_id: str,
        new_limit_pln: float,
        declared_income_pln: float,
    ) -> RaiseResult:
        params = {
            "customer_id": customer_id,
            "new_limit_pln": new_limit_pln,
            "declared_income_pln": declared_income_pln,
        }
        ikey = compute_raise_idempotency_key(dfid, RAISE_STEP_ID, params)
        if ikey in _seen_keys:
            return RaiseResult(
                ok=True,
                new_limit_pln=new_limit_pln,
                idempotency_key=ikey,
                cached=True,
                message="Idempotent replay — limit already raised",
            )
        _seen_keys.add(ikey)
        logger.info(
            "[DFID=%s] Mock raise limit customer=%s new_limit=%.0f",
            dfid[:8],
            customer_id,
            new_limit_pln,
        )
        return RaiseResult(
            ok=True,
            new_limit_pln=new_limit_pln,
            idempotency_key=ikey,
            cached=False,
            message="Limit raised",
        )
