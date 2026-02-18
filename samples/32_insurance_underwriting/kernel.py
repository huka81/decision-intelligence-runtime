"""
Kernel Space components for the Digital Underwriter (Topology C / DL+PCI).

AgentRegistry, ContextStore, DecisionLedger, and DecisionIntegrityModule (DIM).
The DIM is the Proof Checker: it recalculates the Evidence Hash using authoritative
sources and rejects any PCI whose hash does not match (Zero Trust).
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from models import (
    ClientApplication,
    PolicyProposal,
    ProofCarryingIntent,
    UnderwritingContract,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Hash Utilities (shared by Agent and DIM)
# =============================================================================


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
    Evidence Hash formula per Topology C spec.

    Evidence_Hash = SHA256(DFID || Context_Hash || Contract_Hash || Proposal_Params)

    The DIM recalculates this using authoritative Registry and ContextStore data.
    It never trusts the agent's claimed hash.
    """
    payload = f"{dfid}{context_hash}{contract_hash}{proposal_params}"
    return hashlib.sha256(payload.encode()).hexdigest()


def proposal_params_for_hash(proposal: PolicyProposal) -> str:
    """Canonical string of proposal fields used for compliance verification."""
    params = {
        "coverage_limit": proposal.coverage_limit,
        "premium": proposal.premium,
        "industry": proposal.industry,
    }
    return _canonical_json(params)


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
# DecisionLedger (append-only, verified decisions only)
# =============================================================================


class DecisionLedger:
    """
    Append-only list storing only verified decisions.

    Why Ledger stores only verified: Unverified decisions must never become
    binding. The Ledger is the source of truth; only DIM-approved entries
    are appended. This prevents "Day Two" failures where hallucinated or
    forged agent outputs become operational contracts.
    """

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []

    def append(self, pci: ProofCarryingIntent) -> None:
        """Append a verified PCI. Called only by DIM after successful verification."""
        entry = {
            "dfid": pci.dfid,
            "policy_proposal": pci.policy_proposal.model_dump(),
            "evidence_hash": pci.evidence_hash,
        }
        self._entries.append(entry)
        logger.info(
            "[DFID=%s] Ledger appended entry #%d. Policy Bound.",
            pci.dfid[:8],
            len(self._entries),
        )

    def entries(self) -> List[Dict[str, Any]]:
        """Return all ledger entries (read-only)."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# =============================================================================
# DecisionIntegrityModule (DIM) - Proof Checker
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
        1. Set context in store (for this verification) and get authoritative hashes.
        2. Recompute expected_evidence_hash from DFID + Context_Hash + Contract_Hash + Proposal_Params.
        3. Compare with pci.evidence_hash. Mismatch -> "Evidence Invalid".
        4. If match: run business-rule checks (prohibited industry, max limit).
        5. If all pass: append to Ledger, return "Policy Bound".
        6. Otherwise: return rejection reason.
        """
        # Ensure we verify against the context provided (authoritative for this flow)
        self.context_store.set_context(context)

        context_hash = self.context_store.get_context_hash()
        contract_hash = self.registry.get_contract_hash()
        proposal_params = proposal_params_for_hash(pci.policy_proposal)

        expected_hash = compute_evidence_hash(
            pci.dfid, context_hash, contract_hash, proposal_params
        )

        if expected_hash != pci.evidence_hash:
            logger.warning(
                "[DFID=%s] REJECT: Evidence Invalid (hash mismatch). Zero Trust.",
                pci.dfid[:8],
            )
            return "Evidence Invalid"

        # Business rule checks (prohibited industry, max limit)
        proposal = pci.policy_proposal
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
