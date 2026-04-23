"""
Fake payment gateway: no HTTP; idempotent in-memory replay via ``AuditStore``.

Real systems would call PSP APIs here; the sample only logs and writes audit
rows.
"""

from __future__ import annotations

import hashlib
import json
import logging

from dir_core.storage import AuditStore
from dir_core.utils.logging_utils import log_with_dfid

from telemetry import record_payment_executed

PAYMENT_STEP_ID = "PAYMENT_ALLOW"


def payment_idempotency_key(
    dfid: str,
    tx_id: str,
    user_id: str,
    amount: float,
) -> str:
    payload = json.dumps(
        {
            "dfid": dfid,
            "step": PAYMENT_STEP_ID,
            "tx_id": tx_id,
            "user_id": user_id,
            "amount": amount,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def execute_mock_allow_settlement(
    logger: logging.Logger,
    audit: AuditStore,
    dfid: str,
    *,
    simulation_id: str,
    tx_id: str,
    user_id: str,
    amount: float,
) -> None:
    """Record first ALLOW settlement; replays use the idempotency cache."""
    ikey = payment_idempotency_key(dfid, tx_id, user_id, amount)
    cached = audit.get_idempotent_result(ikey)
    if cached is not None:
        record_payment_executed(
            audit,
            dfid,
            simulation_id=simulation_id,
            tx_id=tx_id,
            user_id=user_id,
            amount=amount,
            idempotency_key_prefix=ikey[:16],
            cached=True,
        )
        return
    result_body = {"tx_id": tx_id, "status": "SETTLED", "user_id": user_id}
    audit.save_idempotent_result(ikey, dfid, result_body)
    record_payment_executed(
        audit,
        dfid,
        simulation_id=simulation_id,
        tx_id=tx_id,
        user_id=user_id,
        amount=amount,
        idempotency_key_prefix=ikey[:16],
        cached=False,
    )


def log_mock_gateway_non_allow(
    logger: logging.Logger,
    dfid: str,
    policy_kind: str,
    tx_id: str,
) -> None:
    msg = (
        "PaymentGateway (mock): %s tx_id=%s "
        "(no settlement for non-ALLOW policy)"
    )
    log_with_dfid(logger, dfid, logging.INFO, msg, policy_kind, tx_id)
