"""
Mock Insurance Policy Bind API (Kernel Space, Topology C execution step).

Idempotency: SHA256(DFID + Step_ID + canonical bind params) per DIR-minified.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from audit_store import AuditStore

logger = logging.getLogger(__name__)

BIND_STEP_ID = "BIND_POLICY"


def _canonical_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def compute_bind_idempotency_key(
    dfid: str, step_id: str, params: dict[str, Any]
) -> str:
    payload = f"{dfid}:{step_id}:{_canonical_params(params)}"
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class BindResult:
    ok: bool
    policy_ref: str
    idempotency_key: str
    cached: bool
    message: str


class PolicyBindingClient:
    """Deterministic mock bind — no network; records audit events."""

    def __init__(self, audit: AuditStore) -> None:
        self._audit = audit

    def bind_policy(
        self,
        dfid: str,
        *,
        total_insured_value: float,
        premium: float,
        industry: str,
    ) -> BindResult:
        params = {
            "total_insured_value": total_insured_value,
            "premium": premium,
            "industry": industry,
        }
        ikey = compute_bind_idempotency_key(dfid, BIND_STEP_ID, params)

        self._audit.record(
            dfid,
            "BIND_REQUEST",
            step_id=BIND_STEP_ID,
            state="EXECUTING",
            details={
                "idempotency_key_prefix": ikey[:16],
                "total_insured_value": total_insured_value,
                "premium": premium,
            },
        )
        log_bind_req = (
            '{"dfid":"%s","event":"BIND_REQUEST","step_id":"%s",'
            '"idempotency_key":"%s"}'
        )
        logger.info(log_bind_req, dfid, BIND_STEP_ID, ikey[:16] + "...")

        cached = self._audit.get_idempotent_result(ikey)
        if cached is not None:
            self._audit.record(
                dfid,
                "BIND_SUCCEEDED",
                step_id=BIND_STEP_ID,
                state="CLOSED",
                details={
                    "cached": True,
                    "policy_ref": cached.get("policy_ref"),
                },
            )
            log_ok = (
                '{"dfid":"%s","event":"BIND_SUCCEEDED",'
                '"cached":true,"policy_ref":"%s"}'
            )
            logger.info(log_ok, dfid, cached.get("policy_ref", ""))
            return BindResult(
                ok=True,
                policy_ref=str(cached.get("policy_ref", "")),
                idempotency_key=ikey,
                cached=True,
                message="Idempotent replay - returned prior bind result.",
            )

        policy_ref = f"POL-{uuid.uuid4().hex[:12].upper()}"
        result_body = {"policy_ref": policy_ref, "status": "BOUND"}
        self._audit.save_idempotent_result(ikey, dfid, result_body)

        self._audit.record(
            dfid,
            "BIND_SUCCEEDED",
            step_id=BIND_STEP_ID,
            state="CLOSED",
            details={"cached": False, "policy_ref": policy_ref},
        )
        log_new = (
            '{"dfid":"%s","event":"BIND_SUCCEEDED",'
            '"cached":false,"policy_ref":"%s"}'
        )
        logger.info(log_new, dfid, policy_ref)

        return BindResult(
            ok=True,
            policy_ref=policy_ref,
            idempotency_key=ikey,
            cached=False,
            message="Policy bound via mock underwriting API.",
        )
