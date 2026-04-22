#!/usr/bin/env python3
"""
11_topology_c_dl_pci — Technical minimal demo: Topology C (DL+PCI).

Focus: build Proof-Carrying Intent, verify proof/hash against context and
contract, pass proposal through DecisionRuntime DIM gate, append accepted PCI to
DecisionLedger.

Aligned with .cursor/rules/06-technical-sample-development-guide.mdc.
No samples/shared, no YAML, memory_storage + DecisionRuntime only.

Run: python samples/11_topology_c_dl_pci/run.py
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import (  # noqa: E402
    DecisionLedger,
    DecisionRuntime,
    PolicyProposal,
    ProofCarryingIntent,
    ProofChecker,
    ResponsibilityContract,
    compute_evidence_hash,
    hash_content,
    proposal_params_for_hash,
    new_dfid,
)
from dir_core.data_types import ContractRole, ValidationVerdict  # noqa: E402
from dir_core.storage import memory_storage  # noqa: E402
from dir_core.utils.logging_utils import log_with_dfid  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_AGENT_ID = "agent_banker"
_KEYS = {_AGENT_ID: b"bank_super_secret"}


def _sign(secret_key: bytes, payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hmac.new(secret_key, canonical.encode(), hashlib.sha256).hexdigest()


def _verify_signature(secret_key: bytes, payload: Dict[str, Any], signature: str) -> bool:
    expected = _sign(secret_key, payload)
    return hmac.compare_digest(expected, signature)


def _contract() -> Dict[str, Any]:
    return ResponsibilityContract(
        agent_id=_AGENT_ID,
        role=ContractRole.EXECUTOR,
        mission="Submit high-stakes transfer intents with PCI evidence.",
        authorized_instruments=["BANK"],
        allowed_policy_types=["TRANSFER_FUNDS"],
        escalate_on_uncertainty=0.7,
        max_drawdown_limit=0.05,
        wake_up_threshold_pct=0.5,
        parent_agent_id=None,
    ).model_dump()


def _contract_hash(contract: Dict[str, Any]) -> str:
    stable = {
        "agent_id": contract["agent_id"],
        "role": contract["role"],
        "allowed_policy_types": contract["allowed_policy_types"],
        "authorized_instruments": contract["authorized_instruments"],
    }
    return hash_content(stable)


def _make_pci(
    context: Dict[str, Any],
    amount: float,
    recipient: str,
    contract_hash: str,
) -> ProofCarryingIntent:
    dfid = new_dfid()
    payload = {
        "agent_id": _AGENT_ID,
        "policy_kind": "TRANSFER_FUNDS",
        "params": {"amount": amount, "recipient": recipient},
        "confidence": 0.95,
        "justification": "Topology C technical demo intent.",
    }
    context_hash = hash_content(context)
    evidence_hash = compute_evidence_hash(
        dfid=dfid,
        context_hash=context_hash,
        contract_hash=contract_hash,
        proposal_params=proposal_params_for_hash(payload),
    )
    signature = _sign(_KEYS[_AGENT_ID], payload)
    return ProofCarryingIntent(
        dfid=dfid,
        intent_payload=payload,
        context_ref=context_hash,
        evidence_hash=evidence_hash,
        signature=signature,
    )


def _submit(
    runtime: DecisionRuntime,
    ledger: DecisionLedger,
    checker: ProofChecker,
    pci: ProofCarryingIntent,
    context: Dict[str, Any],
    contract_hash: str,
) -> bool:
    dfid = pci.dfid
    payload = dict(pci.intent_payload)
    agent_id = str(payload.get("agent_id", ""))
    if agent_id not in _KEYS:
        log_with_dfid(logger, dfid, logging.WARNING, "REJECT unknown agent")
        return False

    if not _verify_signature(_KEYS[agent_id], payload, pci.signature):
        log_with_dfid(logger, dfid, logging.WARNING, "REJECT invalid signature")
        return False

    ok, reason = checker.verify(
        pci,
        get_context_hash=lambda: hash_content(context),
        get_contract_hash=lambda: contract_hash,
        get_proposal_params=proposal_params_for_hash,
    )
    if not ok:
        log_with_dfid(logger, dfid, logging.WARNING, "REJECT proof: %s", reason)
        return False

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=agent_id,
        policy_kind=str(payload.get("policy_kind", "")),
        params=dict(payload.get("params", {})),
        context_ref=pci.context_ref,
        confidence=float(payload.get("confidence", 1.0)),
        justification=str(payload.get("justification", "PCI verified")),
    )
    verdict, reason = runtime.evaluate_proposal(
        proposal,
        {},
        dim_context={"state": {"risk_score": 0.0}},
        allowed_agents=[_AGENT_ID],
        contract=_contract(),
        use_registry_contract=False,
    )
    if verdict == ValidationVerdict.ACCEPT:
        ledger.append(pci)
        log_with_dfid(logger, dfid, logging.INFO, "ACCEPT ledger_append")
        return True

    log_with_dfid(logger, dfid, logging.INFO, "REJECT by DIM: %s", reason)
    return False


def main() -> None:
    runtime = DecisionRuntime(memory_storage())
    contract = _contract()
    c_hash = _contract_hash(contract)
    hr = runtime.register_agent(_AGENT_ID, contract, agent_version="1.0.0")
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    ledger = DecisionLedger()
    checker = ProofChecker()
    accepted = 0
    rejected = 0

    context_a = {"balance": 1000, "status": "active"}
    context_b = {"balance": 900, "status": "active"}

    # Scene 1: valid PCI
    pci_valid = _make_pci(context_a, amount=100.0, recipient="alice", contract_hash=c_hash)
    if _submit(runtime, ledger, checker, pci_valid, context_a, c_hash):
        accepted += 1
    else:
        rejected += 1

    # Scene 2: tampered payload (signature mismatch)
    pci_tampered = copy.deepcopy(pci_valid)
    pci_tampered.dfid = new_dfid()
    pci_tampered.intent_payload["params"]["amount"] = 999_999.0
    if _submit(runtime, ledger, checker, pci_tampered, context_a, c_hash):
        accepted += 1
    else:
        rejected += 1

    # Scene 3: replay in different context (evidence mismatch)
    if _submit(runtime, ledger, checker, pci_valid, context_b, c_hash):
        accepted += 1
    else:
        rejected += 1

    print(
        f"\n[SUMMARY] accepted={accepted} rejected={rejected} "
        f"ledger_entries={len(ledger)}",
    )


if __name__ == "__main__":
    main()
