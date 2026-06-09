"""Tier 3 — Proof-Carrying Intent build and verify (Topology C)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Tuple

from dir_core import (
    ProofCarryingIntent,
    ProofChecker,
    compute_evidence_hash,
    hash_content,
    proposal_params_for_hash,
)

_SIGNING_KEY = b"credit_limit_demo_secret"
AGENT_ID = "credit_limit_agent"


def contract_hash_for_agent(contract: Dict[str, Any]) -> str:
    stable = {
        "agent_id": AGENT_ID,
        "role": contract.get("role"),
        "allowed_policy_types": contract.get("allowed_policy_types"),
        "authorized_instruments": contract.get("authorized_instruments"),
    }
    return hash_content(stable)


def _sign(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hmac.new(_SIGNING_KEY, canonical.encode(), hashlib.sha256).hexdigest()


def build_pci(
    dfid: str,
    claim: Dict[str, Any],
    context: Dict[str, Any],
    contract_hash: str,
    justification: str,
    *,
    confidence: float = 0.92,
) -> ProofCarryingIntent:
    payload = {
        "agent_id": AGENT_ID,
        "policy_kind": "RAISE_LIMIT",
        "params": claim,
        "confidence": confidence,
        "justification": justification,
    }
    context_hash = hash_content(context)
    evidence_hash = compute_evidence_hash(
        dfid=dfid,
        context_hash=context_hash,
        contract_hash=contract_hash,
        proposal_params=proposal_params_for_hash(payload),
    )
    return ProofCarryingIntent(
        dfid=dfid,
        intent_payload=payload,
        context_ref=context_hash,
        evidence_hash=evidence_hash,
        signature=_sign(payload),
    )


def verify_pci(
    pci: ProofCarryingIntent,
    context: Dict[str, Any],
    contract_hash: str,
) -> Tuple[bool, str]:
    checker = ProofChecker()
    return checker.verify(
        pci,
        get_context_hash=lambda: hash_content(context),
        get_contract_hash=lambda: contract_hash,
        get_proposal_params=proposal_params_for_hash,
    )
