#!/usr/bin/env python3
"""
12_compliant_lie — Minimal technical demonstration.

Focus: Evidence Hierarchy (Heuristic, Reconstructed, Cryptographic) and The Compliant Lie
Run from repo root: python samples/12_compliant_lie/run.py
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

# --- sys.path wiring: required for `dir_core` (src/) imports only
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import (  # noqa: E402
    DecisionRuntime,
    PolicyProposal,
    ProofCarryingIntent,
    ProofChecker,
    compute_evidence_hash,
    hash_content,
    new_dfid,
    proposal_params_for_hash,
)
from dir_core.data_types import ValidationVerdict  # noqa: E402
from dir_core.storage import memory_storage  # noqa: E402
from dir_core.utils.logging_utils import log_with_dfid  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_AGENT_ID = "underwriting_agent"
_SIGNING_KEY = b"underwriting_demo_secret"

EMAIL_CONTEXT = (
    "Please provide an urgent insurance quote for our new fleet: "
    "50 heavy trucks carrying hazardous materials."
)

# The Compliant Lie: structurally valid, semantically wrong
COMPLIANT_LIE_CLAIM: Dict[str, Any] = {
    "vehicle_type": "personal_cars",
    "vehicle_count": 5,
    "hazardous_materials": False,
}

# Honest claim aligned with context (used in Tier 3 valid PCI path)
HONEST_CLAIM: Dict[str, Any] = {
    "vehicle_type": "heavy_trucks",
    "vehicle_count": 50,
    "hazardous_materials": True,
}


def _contract_dict() -> Dict[str, Any]:
    return {
        "role": "EXECUTOR",
        "mission": "Evaluate insurance requests and propose policies.",
        "allowed_policy_types": ["ISSUE_POLICY", "REJECT"],
        "escalate_on_uncertainty": 0.7,
        "max_drawdown_limit": 0.05,
        "wake_up_threshold_pct": 0.5,
        "authorized_instruments": ["COMMERCIAL_FLEET"],
    }


def _contract_hash(contract: Dict[str, Any]) -> str:
    stable = {
        "agent_id": _AGENT_ID,
        "role": contract["role"],
        "allowed_policy_types": contract["allowed_policy_types"],
        "authorized_instruments": contract["authorized_instruments"],
    }
    return hash_content(stable)


def _sign(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hmac.new(_SIGNING_KEY, canonical.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Tier 1 — Heuristic Evidence (Differential Heuristics)
# ---------------------------------------------------------------------------

def heuristic_evidence(text: str) -> Dict[str, Any]:
    """Legacy deterministic checks: regex / keyword extraction."""
    evidence: Dict[str, Any] = {}
    text_lower = text.lower()
    if "heavy truck" in text_lower:
        evidence["vehicle_type"] = "heavy_trucks"
    if "hazardous" in text_lower:
        evidence["hazardous_materials"] = True
    return evidence


def check_heuristic_evidence(
    claim: Dict[str, Any], context_text: str
) -> Tuple[bool, str]:
    evidence = heuristic_evidence(context_text)
    mismatches = []
    if claim.get("vehicle_type") != evidence.get(
        "vehicle_type", claim.get("vehicle_type")
    ):
        mismatches.append("vehicle_type")
    if claim.get("hazardous_materials") != evidence.get(
        "hazardous_materials", claim.get("hazardous_materials")
    ):
        mismatches.append("hazardous_materials")
    if mismatches:
        return False, f"HEURISTIC_DELTA: {', '.join(mismatches)}"
    return True, "OK"


# ---------------------------------------------------------------------------
# Tier 2 — Reconstructed Evidence (Bidirectional Reconstruction)
# ---------------------------------------------------------------------------

def reconstruct_narrative_from_claim(claim: Dict[str, Any]) -> str:
    """
    Mock reconstruction agent: reads ONLY the structured claim (no original email).
    In production this would be a separate LLM call.
    """
    vehicle = str(claim.get("vehicle_type", "unknown")).replace("_", " ")
    count = claim.get("vehicle_count", 0)
    cargo = (
        "hazardous materials"
        if claim.get("hazardous_materials")
        else "standard cargo"
    )
    return f"Client requests insurance for {count} {vehicle} carrying {cargo}."


def check_reconstructed_evidence(
    claim: Dict[str, Any], context_text: str
) -> Tuple[bool, str]:
    reconstructed = reconstruct_narrative_from_claim(claim)
    context_lower = context_text.lower()
    recon_lower = reconstructed.lower()

    required_signals = []
    if "heavy truck" in context_lower:
        required_signals.append(("heavy truck", recon_lower))
    if "hazardous" in context_lower:
        required_signals.append(("hazardous", recon_lower))

    for term, narrative in required_signals:
        if term not in narrative:
            return False, f"RECONSTRUCTION_MISMATCH: '{term}' absent in '{reconstructed}'"

    return True, reconstructed


# ---------------------------------------------------------------------------
# Tier 3 — Cryptographic Evidence (PCI evidence_hash)
# ---------------------------------------------------------------------------

def build_pci(
    dfid: str,
    claim: Dict[str, Any],
    context: Dict[str, Any],
    contract_hash: str,
    justification: str,
) -> ProofCarryingIntent:
    payload = {
        "agent_id": _AGENT_ID,
        "policy_kind": "ISSUE_POLICY",
        "params": claim,
        "confidence": 0.95,
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


def verify_cryptographic_evidence(
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


def submit_to_dim(
    runtime: DecisionRuntime,
    pci: ProofCarryingIntent,
    contract: Dict[str, Any],
    ctx: Dict[str, Any],
) -> Tuple[ValidationVerdict, str]:
    payload = pci.intent_payload
    proposal = PolicyProposal(
        dfid=pci.dfid,
        agent_id=_AGENT_ID,
        policy_kind=str(payload.get("policy_kind", "")),
        params=dict(payload.get("params", {})),
        context_ref=pci.context_ref,
        confidence=float(payload.get("confidence", 1.0)),
        justification=str(payload.get("justification", "")),
    )
    return runtime.evaluate_proposal(
        proposal,
        {},
        dim_context=ctx,
        allowed_agents=[_AGENT_ID],
        contract=contract,
        use_registry_contract=False,
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_0_baseline(
    runtime: DecisionRuntime, contract: Dict[str, Any]
) -> None:
    """No Evidence Governance — Compliant Lie bypasses Kernel DIM."""
    dfid = new_dfid()
    log_with_dfid(logger, dfid, logging.INFO, "=== Scenario 0: Baseline (no Evidence Governance) ===")

    runtime.context_store.update_session(dfid, {"input_email": EMAIL_CONTEXT})
    ctx = runtime.context_store.compile_working_context(_AGENT_ID, dfid)

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=_AGENT_ID,
        policy_kind="ISSUE_POLICY",
        params=COMPLIANT_LIE_CLAIM,
        confidence=0.95,
        justification="Client requested insurance for 5 personal cars.",
    )
    verdict, reason = runtime.evaluate_proposal(
        proposal,
        {},
        dim_context=ctx,
        allowed_agents=[_AGENT_ID],
        contract=contract,
        use_registry_contract=False,
    )
    executed = verdict == ValidationVerdict.ACCEPT
    if executed:
        log_with_dfid(
            logger,
            dfid,
            logging.WARNING,
            "[Execution] Catastrophic: policy issued for personal_cars instead of heavy_trucks",
        )
    print(f"[SUMMARY] scenario=0_baseline verdict={verdict} executed={executed} reason={reason}\n")


def scenario_1_heuristic_evidence() -> None:
    """Tier 1 — Heuristic Evidence catches the Compliant Lie before PCI."""
    dfid = new_dfid()
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "=== Scenario 1: Tier 1 — Heuristic Evidence (Differential Heuristics) ===",
    )
    log_with_dfid(logger, dfid, logging.INFO, "[User Space] LLM Claim: %s", COMPLIANT_LIE_CLAIM)
    evidence = heuristic_evidence(EMAIL_CONTEXT)
    log_with_dfid(logger, dfid, logging.INFO, "[User Space] Heuristic Evidence: %s", evidence)

    ok, reason = check_heuristic_evidence(COMPLIANT_LIE_CLAIM, EMAIL_CONTEXT)
    if not ok:
        log_with_dfid(
            logger,
            dfid,
            logging.ERROR,
            "[User Space] ABORT — %s — COMPLIANT_LIE_SUSPECTED",
            reason,
        )
    print(f"[SUMMARY] scenario=1_heuristic passed={ok} reason={reason}\n")


def scenario_2_reconstructed_evidence() -> None:
    """Tier 2 — Reconstructed Evidence catches lie via Bidirectional Reconstruction."""
    dfid = new_dfid()
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "=== Scenario 2: Tier 2 — Reconstructed Evidence (Bidirectional Reconstruction) ===",
    )
    reconstructed = reconstruct_narrative_from_claim(COMPLIANT_LIE_CLAIM)
    log_with_dfid(logger, dfid, logging.INFO, "[User Space] LLM Claim: %s", COMPLIANT_LIE_CLAIM)
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "[User Space] Reconstructed narrative (claim-only): %s",
        reconstructed,
    )

    ok, reason = check_reconstructed_evidence(COMPLIANT_LIE_CLAIM, EMAIL_CONTEXT)
    if not ok:
        log_with_dfid(
            logger,
            dfid,
            logging.ERROR,
            "[User Space] ABORT — %s — COMPLIANT_LIE_SUSPECTED",
            reason,
        )
    print(f"[SUMMARY] scenario=2_reconstructed passed={ok} reason={reason}\n")


def scenario_3_cryptographic_evidence(
    runtime: DecisionRuntime, contract: Dict[str, Any], contract_hash: str
) -> None:
    """Tier 3 — Cryptographic Evidence: valid PCI vs tampered PCI."""
    context = {"input_email": EMAIL_CONTEXT}
    ctx = runtime.context_store.compile_working_context(_AGENT_ID, new_dfid())

    # 3a — Honest claim passes Tiers 1+2, PCI hash verifies, DIM accepts
    dfid_valid = new_dfid()
    log_with_dfid(
        logger,
        dfid_valid,
        logging.INFO,
        "=== Scenario 3a: Tier 3 — Cryptographic Evidence (valid PCI) ===",
    )
    runtime.context_store.update_session(dfid_valid, context)

    h_ok, h_reason = check_heuristic_evidence(HONEST_CLAIM, EMAIL_CONTEXT)
    r_ok, r_reason = check_reconstructed_evidence(HONEST_CLAIM, EMAIL_CONTEXT)
    log_with_dfid(
        logger,
        dfid_valid,
        logging.INFO,
        "[User Space] Tiers 1+2 passed: heuristic=%s reconstruction=%s",
        h_ok,
        r_ok,
    )

    pci_valid = build_pci(
        dfid_valid,
        HONEST_CLAIM,
        context,
        contract_hash,
        justification="Fleet underwriting for 50 heavy trucks with hazmat.",
    )
    crypto_ok, crypto_reason = verify_cryptographic_evidence(
        pci_valid, context, contract_hash
    )
    log_with_dfid(
        logger,
        dfid_valid,
        logging.INFO,
        "[Kernel Space] ProofChecker: %s (%s)",
        crypto_ok,
        crypto_reason,
    )

    verdict, dim_reason = submit_to_dim(runtime, pci_valid, contract, ctx)
    executed = crypto_ok and verdict == ValidationVerdict.ACCEPT
    print(
        f"[SUMMARY] scenario=3a_cryptographic_valid "
        f"proof_ok={crypto_ok} verdict={verdict} executed={executed}\n"
    )

    # 3b — Tampered PCI: params changed after hash computation
    dfid_tampered = new_dfid()
    log_with_dfid(
        logger,
        dfid_tampered,
        logging.INFO,
        "=== Scenario 3b: Tier 3 — Cryptographic Evidence (tampered PCI) ===",
    )
    pci_tampered = copy.deepcopy(pci_valid)
    pci_tampered.dfid = dfid_tampered
    pci_tampered.intent_payload = dict(pci_tampered.intent_payload)
    pci_tampered.intent_payload["params"] = {
        **HONEST_CLAIM,
        "vehicle_count": 5,
        "vehicle_type": "personal_cars",
    }
    log_with_dfid(
        logger,
        dfid_tampered,
        logging.WARNING,
        "[Attack] Tampered params after signing: %s",
        pci_tampered.intent_payload["params"],
    )

    tamper_ok, tamper_reason = verify_cryptographic_evidence(
        pci_tampered, context, contract_hash
    )
    log_with_dfid(
        logger,
        dfid_tampered,
        logging.INFO,
        "[Kernel Space] ProofChecker: %s (%s)",
        tamper_ok,
        tamper_reason,
    )
    print(
        f"[SUMMARY] scenario=3b_cryptographic_tampered "
        f"proof_ok={tamper_ok} reason={tamper_reason}\n"
    )


def main() -> None:
    bundle = memory_storage()
    runtime = DecisionRuntime(bundle)
    contract = _contract_dict()
    contract_hash = _contract_hash(contract)

    hr = runtime.register_agent(_AGENT_ID, contract, agent_version="1.0.0")
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    scenario_0_baseline(runtime, contract)
    scenario_1_heuristic_evidence()
    scenario_2_reconstructed_evidence()
    scenario_3_cryptographic_evidence(runtime, contract, contract_hash)


if __name__ == "__main__":
    main()
