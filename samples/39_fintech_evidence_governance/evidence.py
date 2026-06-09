"""Evidence Governance Tiers 1 and 2 (User Space, pre-PCI)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from schemas import EvidenceGovernanceConfig, extract_income_from_chat


@dataclass
class EvidenceResult:
    passed: bool
    reason: str
    heuristic_evidence: Dict[str, Any]
    reconstructed_narrative: str = ""


def heuristic_evidence(chat_text: str) -> Dict[str, Any]:
    """Legacy deterministic checks: keyword / regex income extraction."""
    evidence: Dict[str, Any] = {}
    income = extract_income_from_chat(chat_text)
    if income is not None:
        evidence["declared_income_pln"] = income
    text_lower = chat_text.lower()
    if "limit" in text_lower:
        evidence["limit_intent"] = True
    return evidence


def check_heuristic_evidence(
    claim: Dict[str, Any], chat_text: str
) -> Tuple[bool, str]:
    evidence = heuristic_evidence(chat_text)
    mismatches = []
    claim_income = claim.get("declared_income_pln")
    ev_income = evidence.get("declared_income_pln")
    if ev_income is not None and claim_income != ev_income:
        mismatches.append("declared_income_pln")
    if mismatches:
        return False, f"HEURISTIC_DELTA: {', '.join(mismatches)}"
    return True, "OK"


def reconstruct_narrative_from_claim(claim: Dict[str, Any]) -> str:
    """
    Mock reconstruction agent: reads ONLY the structured claim (no original chat).
    In production this would be a separate LLM call.
    """
    income = claim.get("declared_income_pln", 0)
    limit = claim.get("requested_limit_pln", 0)
    return (
        f"Customer requests credit limit increase to {limit} PLN "
        f"based on declared monthly income of {income} PLN."
    )


def check_reconstructed_evidence(
    claim: Dict[str, Any], chat_text: str
) -> Tuple[bool, str]:
    reconstructed = reconstruct_narrative_from_claim(claim)
    context_income = extract_income_from_chat(chat_text)
    if context_income is None:
        return True, reconstructed

    recon_income = int(claim.get("declared_income_pln", 0))
    context_magnitude = "thousand" if context_income < 10000 else "ten-thousand"
    recon_magnitude = "thousand" if recon_income < 10000 else "ten-thousand"

    if context_income < 10000 and recon_income >= 10000:
        return (
            False,
            f"RECONSTRUCTION_MISMATCH: income magnitude '{recon_income}' "
            f"inconsistent with chat income '{context_income}' in '{reconstructed}'",
        )
    if context_magnitude != recon_magnitude and abs(context_income - recon_income) > 1000:
        return (
            False,
            f"RECONSTRUCTION_MISMATCH: '{context_income}' vs '{recon_income}' "
            f"in '{reconstructed}'",
        )
    return True, reconstructed


def run_evidence_gates(
    claim: Dict[str, Any],
    chat_text: str,
    *,
    enable_heuristic: bool = True,
    enable_reconstruction: bool = True,
    _config: EvidenceGovernanceConfig | None = None,
) -> EvidenceResult:
    heuristic_data = heuristic_evidence(chat_text)
    if enable_heuristic:
        ok, reason = check_heuristic_evidence(claim, chat_text)
        if not ok:
            return EvidenceResult(
                passed=False,
                reason=f"{reason} — COMPLIANT_LIE_SUSPECTED",
                heuristic_evidence=heuristic_data,
            )
    if enable_reconstruction:
        ok, reason = check_reconstructed_evidence(claim, chat_text)
        recon = reconstruct_narrative_from_claim(claim)
        if not ok:
            return EvidenceResult(
                passed=False,
                reason=f"{reason} — COMPLIANT_LIE_SUSPECTED",
                heuristic_evidence=heuristic_data,
                reconstructed_narrative=recon,
            )
        return EvidenceResult(
            passed=True,
            reason="OK",
            heuristic_evidence=heuristic_data,
            reconstructed_narrative=recon,
        )
    return EvidenceResult(
        passed=True,
        reason="OK",
        heuristic_evidence=heuristic_data,
        reconstructed_narrative=reconstruct_narrative_from_claim(claim),
    )
