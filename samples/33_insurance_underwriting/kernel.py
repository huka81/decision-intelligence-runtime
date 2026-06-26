"""
Kernel Space components for the Digital Underwriter (Topology C / DL+PCI).

AgentRegistry, ContextStore (domain-specific). DecisionLedger, ProofChecker,
compute_evidence_hash, hash_content, proposal_params_for_hash from dir_core (framework).
"""

import logging
from typing import Any, Dict, List, Optional

from dir_core import AgentRegistry, ContextStore
from dir_core.ledger import DecisionLedger
from dir_core.models import ProofCarryingIntent
from dir_core.pci import (
    ProofChecker,
    compute_evidence_hash,
    hash_content,
    proposal_params_for_hash,
)

from schemas import PolicyProposal

logger = logging.getLogger(__name__)

# Binding fields for Evidence_Hash (Topology C). Textual / observability fields
# stay in PCI JSON but are excluded from the canonical proposal string.
EXECUTION_RELEVANT_INTENT_KEYS = ("total_insured_value", "premium", "industry")


def intent_subset_for_evidence_hash(intent_payload: Dict[str, Any]) -> str:
    """Canonical JSON of execution-relevant proposal fields for PCI Evidence_Hash."""
    subset = {
        k: intent_payload[k]
        for k in EXECUTION_RELEVANT_INTENT_KEYS
        if k in intent_payload
    }
    return proposal_params_for_hash(subset)


# Re-export for backward compatibility (agent imports from kernel)
__all__ = [
    "DecisionIntegrityModule",
    "DecisionLedger",
    "EXECUTION_RELEVANT_INTENT_KEYS",
    "compute_evidence_hash",
    "hash_content",
    "intent_subset_for_evidence_hash",
    "proposal_params_for_hash",
]


# =============================================================================
# DecisionIntegrityModule (DIM) - Proof Checker + Business Rules
# =============================================================================


class DecisionIntegrityModule:
    """
    The Proof Checker. Validates PCIs using Zero Trust.

    Why DIM recalculates: The agent's evidence_hash is a claim. The DIM
    independently recomputes using authoritative sources (ContextStore,
    AgentRegistry). Mismatch = reject. The DIM never trusts the agent.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        context_store: ContextStore,
        ledger: DecisionLedger,
    ):
        self.registry = registry
        self.context_store = context_store
        self.ledger = ledger

    def verify_and_commit(
        self, pci: ProofCarryingIntent, agent_id: str
    ) -> str:
        """
        Verify the PCI and commit to Ledger if valid.

        Steps:
        1. Context was set in store.
        2. Use ProofChecker to verify evidence_hash (Zero Trust).
        3. If match: run business-rule checks (prohibited industry, max TiV).
        4. If all pass: append to Ledger, return "Policy Bound".
        5. Otherwise: return rejection reason.
        """
        def get_proposal_params(intent_payload: Dict[str, Any]) -> str:
            return intent_subset_for_evidence_hash(intent_payload)

        def get_context_hash() -> str:
            session = self.context_store.get_session(pci.dfid)
            return hash_content(session) if session else ""

        def get_contract_hash() -> str:
            contract = self.registry.get_agent_contract(agent_id)
            return hash_content(contract) if contract else ""

        ok, reason = ProofChecker().verify(
            pci,
            get_context_hash=get_context_hash,
            get_contract_hash=get_contract_hash,
            get_proposal_params=get_proposal_params,
        )
        if not ok:
            return reason

        contract = self.registry.get_agent_contract(agent_id)
        if not contract:
            return "Contract Not Found"

        max_tiv = contract.get("max_tiv", 0)
        prohibited_industries = contract.get("prohibited_industries", [])

        # Business rule checks (prohibited industry, max TiV)
        proposal = PolicyProposal.model_validate(pci.intent_payload)
        prohibited_lower = {x.strip().lower() for x in prohibited_industries}
        if proposal.industry.strip().lower() in prohibited_lower:
            logger.warning(
                "[DFID=%s] REJECT: Prohibited Industry (%s).",
                pci.dfid[:8],
                proposal.industry,
            )
            return "Prohibited Industry"

        if proposal.total_insured_value > max_tiv:
            logger.warning(
                "[DFID=%s] REJECT: TiV %.0f exceeds contract max_tiv %.0f.",
                pci.dfid[:8],
                proposal.total_insured_value,
                max_tiv,
            )
            return "TIV Exceeds Contract Max"

        # All checks passed: commit to Ledger
        self.ledger.append(pci, agent_id=agent_id)
        logger.info("[DFID=%s] Policy Bound.", pci.dfid[:8])
        return "Policy Bound"

