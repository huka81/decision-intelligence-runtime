"""
Proof-Carrying Intent (PCI) utilities for Topology C (DL+PCI).

Evidence Hash computation and ProofChecker per Technical Annex.
"""

import hashlib
import json
import logging
from typing import Any, Callable, Dict, Tuple

from .models import ProofCarryingIntent

logger = logging.getLogger(__name__)


def _canonical_json(obj: Any) -> str:
    """Canonical JSON for deterministic hashing."""
    return json.dumps(obj, sort_keys=True, default=str)


def hash_content(obj: Any) -> str:
    """SHA256 of canonical JSON."""
    return hashlib.sha256(_canonical_json(obj).encode()).hexdigest()


def compute_evidence_hash(
    dfid: str,
    context_hash: str,
    contract_hash: str,
    proposal_params: str,
) -> str:
    """
    Evidence Hash formula per Topology C Technical Annex §3.2.

    Evidence_Hash = SHA256(DFID || Context_Hash || Contract_Hash || Proposal_Params)

    The reference implementation uses proposal_params (canonical JSON of intent)
    in place of H_r (rule-set hash) for MVP. See Technical Annex §3.2 for full spec.

    The DIM recalculates this using authoritative Registry and ContextStore data.
    It never trusts the agent's claimed hash.
    """
    payload = f"{dfid}{context_hash}{contract_hash}{proposal_params}"
    return hashlib.sha256(payload.encode()).hexdigest()


def proposal_params_for_hash(proposal: Dict[str, Any]) -> str:
    """Canonical string of proposal fields for Evidence Hash.

    For domain-specific subsets, pass a dict with only the fields to include.
    """
    return _canonical_json(proposal)


class ProofChecker:
    """
    Generic Proof Checker for PCI verification (Topology C §4.3).

    Recomputes evidence_hash using authoritative sources. Mismatch = reject.
    Business-rule checks remain the responsibility of the caller/DIM.
    """

    def verify(
        self,
        pci: ProofCarryingIntent,
        get_context_hash: Callable[[], str],
        get_contract_hash: Callable[[], str],
        get_proposal_params: Callable[[Dict[str, Any]], str],
    ) -> Tuple[bool, str]:
        """
        Verify PCI evidence_hash against authoritative sources.

        Args:
            pci: The Proof-Carrying Intent to verify.
            get_context_hash: Callable returning current context hash.
            get_contract_hash: Callable returning contract hash.
            get_proposal_params: Callable(intent_payload) returning canonical proposal string.

        Returns:
            (True, "OK") if hash matches, else (False, reason).
        """
        context_hash = get_context_hash()
        contract_hash = get_contract_hash()
        proposal_params = get_proposal_params(pci.intent_payload)

        expected_hash = compute_evidence_hash(
            pci.dfid, context_hash, contract_hash, proposal_params
        )

        if expected_hash != pci.evidence_hash:
            logger.warning(
                "[DFID=%s] REJECT: Evidence Invalid (hash mismatch). Zero Trust.",
                pci.dfid[:8],
            )
            return False, "Evidence Invalid"

        return True, "OK"
