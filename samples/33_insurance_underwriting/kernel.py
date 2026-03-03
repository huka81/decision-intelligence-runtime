"""
Kernel Space components for the Digital Underwriter (Topology C / DL+PCI).

AgentRegistry, ContextStore (domain-specific). DecisionLedger, ProofChecker,
compute_evidence_hash, hash_content, proposal_params_for_hash from dir (framework).
"""

import logging
from typing import Any, Dict, List, Optional

from dir.ledger import DecisionLedger
from dir.models import ProofCarryingIntent
from dir.pci import (
    ProofChecker,
    compute_evidence_hash,
    hash_content,
    proposal_params_for_hash,
)

from models import ClientApplication, PolicyProposal, UnderwritingContract

logger = logging.getLogger(__name__)


# Re-export for backward compatibility (agent imports from kernel)
__all__ = [
    "AgentRegistry",
    "ContextStore",
    "DecisionIntegrityModule",
    "DecisionLedger",
    "compute_evidence_hash",
    "hash_content",
    "proposal_params_for_hash",
]


# =============================================================================
# AgentRegistry (stores Responsibility Contract)
# =============================================================================


class AgentRegistry:
    """
    In-memory store for the Underwriting Policy (Responsibility Contract).

    The DIM queries this for authoritative rules. The agent does not define
    these rules; the Registry is the source of truth.
    """

    def __init__(self, contract: UnderwritingContract):
        self.contract = contract

    @property
    def max_limit(self) -> float:
        return self.contract.max_limit

    @property
    def prohibited_industries(self) -> List[str]:
        return self.contract.prohibited_industries

    def get_contract_hash(self) -> str:
        """SHA256 of the contract for Evidence Hash computation."""
        return hash_content(self.contract.model_dump())


# =============================================================================
# ContextStore (holds Client Application state)
# =============================================================================


class ContextStore:
    """
    In-memory store for Client Application state.

    The DIM uses this for authoritative context when verifying the Evidence Hash.
    The agent receives context from here; the DIM recomputes Context_Hash from
    this store, never from the PCI.
    """

    def __init__(self):
        self._context: Optional[ClientApplication] = None

    def set_context(self, context: ClientApplication) -> None:
        """Set the current client application."""
        self._context = context

    def get_context(self) -> Optional[ClientApplication]:
        """Return the current client application."""
        return self._context

    def get_context_hash(self) -> str:
        """
        SHA256 of the current context for Evidence Hash computation.

        Returns empty hash if no context is set (verification will fail).
        """
        if self._context is None:
            return ""
        return hash_content(self._context.model_dump())


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
        self, pci: ProofCarryingIntent, context: ClientApplication
    ) -> str:
        """
        Verify the PCI and commit to Ledger if valid.

        Steps:
        1. Set context in store (for this verification).
        2. Use ProofChecker to verify evidence_hash (Zero Trust).
        3. If match: run business-rule checks (prohibited industry, max limit).
        4. If all pass: append to Ledger, return "Policy Bound".
        5. Otherwise: return rejection reason.
        """
        self.context_store.set_context(context)

        def get_proposal_params(intent_payload: Dict[str, Any]) -> str:
            subset = {
                k: intent_payload[k]
                for k in ["coverage_limit", "premium", "industry"]
                if k in intent_payload
            }
            return proposal_params_for_hash(subset)

        ok, reason = ProofChecker().verify(
            pci,
            get_context_hash=self.context_store.get_context_hash,
            get_contract_hash=self.registry.get_contract_hash,
            get_proposal_params=get_proposal_params,
        )
        if not ok:
            return reason

        # Business rule checks (prohibited industry, max limit)
        proposal = PolicyProposal.model_validate(pci.intent_payload)
        if proposal.industry in self.registry.prohibited_industries:
            logger.warning(
                "[DFID=%s] REJECT: Prohibited Industry (%s).",
                pci.dfid[:8],
                proposal.industry,
            )
            return "Prohibited Industry"

        if proposal.coverage_limit > self.registry.max_limit:
            logger.warning(
                "[DFID=%s] REJECT: Coverage limit %.0f exceeds max %.0f.",
                pci.dfid[:8],
                proposal.coverage_limit,
                self.registry.max_limit,
            )
            return "Coverage Limit Exceeded"

        # All checks passed: commit to Ledger
        self.ledger.append(pci)
        logger.info("[DFID=%s] Policy Bound.", pci.dfid[:8])
        return "Policy Bound"
