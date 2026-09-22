"""
Kernel Space: ProofChecker + contract IR + Decision Ledger (Topology C).
"""

import logging
from typing import Any, Dict

from dir_core import AgentRegistry, ContextStore
from dir_core.data_types import ValidationVerdict
from dir_core.dim import validate_proposal
from dir_core.ledger import DecisionLedger
from dir_core.models import PolicyProposal as RuntimePolicyProposal
from dir_core.models import ProofCarryingIntent
from dir_core.pci import ProofChecker, hash_content, proposal_params_for_hash

from schemas import UnderwritingProposal

logger = logging.getLogger(__name__)

EXECUTION_RELEVANT_INTENT_KEYS = ("total_insured_value", "territory")


def intent_subset_for_evidence_hash(intent_payload: Dict[str, Any]) -> str:
    subset = {
        k: intent_payload[k]
        for k in EXECUTION_RELEVANT_INTENT_KEYS
        if k in intent_payload
    }
    return proposal_params_for_hash(subset)


class DecisionIntegrityModule:
    """Proof Checker: recomputes Evidence_Hash; never trusts the agent claim."""

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

        domain = UnderwritingProposal.model_validate(pci.intent_payload)
        session = self.context_store.get_session(pci.dfid) or {}
        runtime_proposal = RuntimePolicyProposal(
            dfid=pci.dfid,
            agent_id=agent_id,
            policy_kind="BIND",
            params={
                "total_insured_value": domain.total_insured_value,
                "territory": domain.territory,
            },
            justification=domain.justification,
        )
        projection = self.registry.get_agent_projection(agent_id)
        verdict, dim_reason = validate_proposal(
            runtime_proposal,
            session,
            contract=projection,
        )
        if verdict != ValidationVerdict.ACCEPT:
            logger.warning("REJECT: %s", dim_reason)
            return str(dim_reason)

        self.ledger.append(pci, agent_id=agent_id)
        logger.info("Policy Bound.")
        return "Policy Bound"
