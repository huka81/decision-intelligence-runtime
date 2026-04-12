"""
Escalation Manager (DIR §9).

Human-in-the-Loop: request escalation, budget (token bucket), resolve.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from .models import EscalationRequest, Policy, PolicyProposal
from .storage.base import EscalationStorage
from .storage.sqlite import SqliteEscalationStorage

logger = logging.getLogger(__name__)


class ImpactCategory(str, Enum):
    """Impact level for escalation (DIR §9.4)."""

    LOW_IMPACT = "LOW_IMPACT"
    HIGH_IMPACT = "HIGH_IMPACT"


class EscalationOutcome(str, Enum):
    """Result of request_escalation."""

    GRANTED = "GRANTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


HumanDecision = Literal["OVERRIDE", "MODIFY", "ABORT"]


class EscalationManager:
    """Manages escalation requests, budget, and resolution (DIR §9).

    Storage backend is pluggable. Pass ``storage=`` for a custom backend, or
    ``db_path=`` to use the built-in SQLite backend (default behaviour).

    Args:
        db_path: Path to SQLite database. Used when ``storage`` is not provided.
        max_escalations_per_hour: Token-bucket capacity per agent per window.
        refill_interval_sec: Window length in seconds (default 3600 = 1 hour).
        storage: Custom :class:`~dir_core.storage.EscalationStorage` backend.
            When provided, ``db_path`` is ignored.

    Raises:
        ValueError: When neither ``db_path`` nor ``storage`` is supplied.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        max_escalations_per_hour: int = 3,
        refill_interval_sec: int = 3600,
        *,
        storage: Optional[EscalationStorage] = None,
    ):
        self.max_escalations_per_hour = max_escalations_per_hour
        self.refill_interval_sec = refill_interval_sec

        if storage is not None:
            self._storage: EscalationStorage = storage
        elif db_path is not None:
            self.db_path = db_path  # kept for backward compatibility
            self._storage = SqliteEscalationStorage(db_path)
        else:
            raise ValueError(
                "Provide either 'db_path' (SQLite) or 'storage' (custom backend)."
            )

    def _get_window_count(self, agent_id: str, now: datetime) -> int:
        """Count escalations in current refill window (last N seconds)."""
        since = now - timedelta(seconds=self.refill_interval_sec)
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        return self._storage.get_window_count(agent_id, since_str)

    def request_escalation(
        self,
        dfid: str,
        agent_id: str,
        reason: str,
        context: Dict[str, Any],
        proposal: PolicyProposal,
        impact: ImpactCategory,
    ) -> EscalationOutcome:
        """
        Request escalation. Returns GRANTED or BUDGET_EXHAUSTED.
        On BUDGET_EXHAUSTED, agent should be demoted to PASSIVE and flow aborted.
        """
        now = datetime.now(timezone.utc)
        count = self._get_window_count(agent_id, now)
        if count >= self.max_escalations_per_hour:
            logger.warning(
                "Escalation budget exhausted: agent_id=%s count=%d",
                agent_id,
                count,
            )
            return EscalationOutcome.BUDGET_EXHAUSTED

        self._storage.record_budget_token(agent_id)
        self._storage.insert_request(
            dfid=dfid,
            agent_id=agent_id,
            reason=reason,
            context_json=json.dumps(context, default=str),
            proposal_json=proposal.model_dump_json(),
            impact=impact.value,
        )
        return EscalationOutcome.GRANTED

    def request_from_model(
        self, escalation: EscalationRequest
    ) -> EscalationOutcome:
        """
        Request escalation from EscalationRequest model (DIR §5.3).

        Maps EscalationRequest to request_escalation API. Converts severity
        (LOW/MEDIUM/HIGH/CRITICAL) to ImpactCategory (LOW_IMPACT/HIGH_IMPACT).
        If original_policy is Policy, converts to PolicyProposal for storage.
        """
        impact = (
            ImpactCategory.HIGH_IMPACT
            if escalation.severity in ("HIGH", "CRITICAL")
            else ImpactCategory.LOW_IMPACT
        )
        if escalation.original_policy is not None:
            orig = escalation.original_policy
            if isinstance(orig, Policy):
                proposal = PolicyProposal(
                    dfid=orig.dfid,
                    agent_id=orig.agent_id,
                    policy_kind=orig.proposed_action,
                    params={},
                    justification=orig.justification,
                    confidence=orig.confidence,
                )
            else:
                proposal = orig  # PolicyProposal or compatible
        else:
            proposal = PolicyProposal(
                dfid=escalation.dfid,
                agent_id=escalation.from_agent_id,
                policy_kind="escalation",
                params={"trigger": escalation.trigger},
            )
        return self.request_escalation(
            dfid=escalation.dfid,
            agent_id=escalation.from_agent_id,
            reason=escalation.trigger,
            context=escalation.context,
            proposal=proposal,
            impact=impact,
        )

    def resolve_escalation(
        self,
        dfid: str,
        decision: HumanDecision,
        modified_proposal: Optional[PolicyProposal] = None,
    ) -> None:
        """Record human decision: OVERRIDE, MODIFY, or ABORT."""
        now = datetime.now(timezone.utc)
        proposal_json = (
            modified_proposal.model_dump_json() if modified_proposal else None
        )
        self._storage.resolve_request(
            dfid=dfid,
            resolved_at=now.isoformat(),
            decision=decision,
            proposal_json=proposal_json,
        )

    def get_pending(self) -> List[Dict[str, Any]]:
        """Return list of pending escalation requests."""
        return self._storage.get_pending_requests()
