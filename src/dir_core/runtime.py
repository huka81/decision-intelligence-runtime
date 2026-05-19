"""
DecisionRuntime — facade wiring StorageBundle to kernel services (DIR DX).

Single entry point for AgentRegistry, ContextStore, EscalationManager,
AuditStore, plus orchestrated DIM validation with optional decision-audit
rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .agent_registry import AgentRegistry, HandshakeResult
from .context_store import ContextStore
from .data_types import ValidationResult, ValidationVerdict
from .dim import validate_proposal
from .escalation import EscalationManager
from .intent_retry import IntentRetryGovernor
from .models import PolicyProposal
from .storage import StorageBundle
from .storage.base import AuditStore

CustomValidator = Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]


class DecisionRuntime:
    """Wire :class:`~dir_core.storage.StorageBundle` to kernel services."""

    def __init__(
        self,
        storage_bundle: StorageBundle,
        *,
        supported_versions: str = "1.x",
        max_escalations_per_hour: int = 3,
        escalation_refill_interval_sec: int = 3600,
    ) -> None:
        self.registry = AgentRegistry(
            storage=storage_bundle.agent_registry,
            supported_versions=supported_versions,
        )
        self.context_store = ContextStore(storage=storage_bundle.context)
        self.escalation = EscalationManager(
            storage=storage_bundle.escalation,
            max_escalations_per_hour=max_escalations_per_hour,
            refill_interval_sec=escalation_refill_interval_sec,
        )
        self.audit = AuditStore(
            storage_bundle.decision_audit,
            storage_bundle.idempotency,
        )

    def register_agent(
        self,
        agent_id: str,
        contract: dict[str, Any],
        agent_version: str,
        *,
        priority: int = 0,
    ) -> HandshakeResult:
        return self.registry.handshake(
            agent_id, contract, agent_version, priority=priority
        )

    def evaluate_proposal(
        self,
        proposal: PolicyProposal,
        raw_web_context: dict[str, Any],
        *,
        dim_context: dict[str, Any] | None = None,
        allowed_agents: list[str] | None = None,
        contract: dict[str, Any] | None = None,
        use_registry_contract: bool = True,
        retry_governor: IntentRetryGovernor | None = None,
        custom_validators: Optional[list[CustomValidator]] = None,
        now: datetime | None = None,
        record_audit: bool = True,
    ) -> ValidationResult:
        self.context_store.update_session(
            proposal.dfid, dict(raw_web_context), agent_id=proposal.agent_id
        )

        if dim_context is not None:
            context: dict[str, Any] = dict(dim_context)
            meta = dict(context.get("meta") or {})
            meta.setdefault("dfid", proposal.dfid)
            meta.setdefault("agent_id", proposal.agent_id)
            context["meta"] = meta
        else:
            ctx = self.context_store.compile_working_context(
                proposal.agent_id, proposal.dfid
            )
            ctx = dict(ctx)
            ctx["web"] = dict(raw_web_context)
            meta = dict(ctx.get("meta") or {})
            meta["dfid"] = proposal.dfid
            meta["agent_id"] = proposal.agent_id
            schema = self.registry.get_schema(proposal.agent_id)
            if schema is not None:
                meta["schema"] = schema
            ctx["meta"] = meta
            context = ctx

        resolved_contract = contract
        if resolved_contract is None and use_registry_contract:
            resolved_contract = self.registry.get_agent_contract(proposal.agent_id)

        verdict, reason = validate_proposal(
            proposal,
            context,
            allowed_agents=allowed_agents,
            now=now,
            retry_governor=retry_governor,
            contract=resolved_contract,
            custom_validators=custom_validators,
        )

        if record_audit and verdict in (
            ValidationVerdict.ACCEPT,
            ValidationVerdict.REJECT,
        ):
            event = (
                "PROPOSAL_ACCEPT"
                if verdict == ValidationVerdict.ACCEPT
                else "PROPOSAL_REJECT"
            )
            details: dict[str, Any] = {
                "agent_id": proposal.agent_id,
                "policy_kind": proposal.policy_kind,
                "reason": str(reason),
                "verdict": str(verdict),
                "confidence": proposal.confidence,
            }
            self.audit.record(
                proposal.dfid,
                event,
                details=details,
                agent_id=proposal.agent_id,
            )

        result: ValidationResult = (verdict, reason)
        return result
