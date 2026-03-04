"""
Escalation Manager (DIR §9).

Human-in-the-Loop: request escalation, budget (token bucket), resolve.
"""

import json
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from .models import EscalationRequest, Policy, PolicyProposal

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
    """Manages escalation requests, budget, and resolution (DIR §9)."""

    def __init__(
        self,
        db_path: str,
        max_escalations_per_hour: int = 3,
        refill_interval_sec: int = 3600,
    ):
        self.db_path = db_path
        self.max_escalations_per_hour = max_escalations_per_hour
        self.refill_interval_sec = refill_interval_sec
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS escalation_budget (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS escalation_requests (
                    dfid TEXT PRIMARY KEY,
                    agent_id TEXT,
                    reason TEXT,
                    context_json TEXT,
                    proposal_json TEXT,
                    impact TEXT,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    human_decision TEXT
                )
            """)
            conn.commit()

    def _get_window_count(self, agent_id: str, now: datetime) -> int:
        """Count escalations in current refill window (last N seconds)."""
        since = now - timedelta(seconds=self.refill_interval_sec)
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM escalation_budget
                WHERE agent_id = ? AND created_at >= ?
                """,
                (agent_id, since_str),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def _record_escalation(self, agent_id: str, now: datetime) -> None:
        """Record one escalation for agent."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO escalation_budget (agent_id) VALUES (?)",
                (agent_id,),
            )
            conn.commit()

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

        self._record_escalation(agent_id, now)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO escalation_requests
                (dfid, agent_id, reason, context_json, proposal_json, impact, status)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    dfid,
                    agent_id,
                    reason,
                    json.dumps(context, default=str),
                    proposal.model_dump_json(),
                    impact.value,
                ),
            )
            conn.commit()
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE escalation_requests
                SET status = 'RESOLVED', resolved_at = ?, human_decision = ?,
                    proposal_json = COALESCE(?, proposal_json)
                WHERE dfid = ?
                """,
                (now.isoformat(), decision, proposal_json, dfid),
            )
            conn.commit()

    def get_pending(self) -> List[Dict[str, Any]]:
        """Return list of pending escalation requests."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT dfid, agent_id, reason, context_json, proposal_json, impact
                FROM escalation_requests WHERE status = 'PENDING'
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "dfid": r["dfid"],
                    "agent_id": r["agent_id"],
                    "reason": r["reason"],
                    "context": json.loads(r["context_json"] or "{}"),
                    "proposal": json.loads(r["proposal_json"] or "{}"),
                    "impact": r["impact"],
                }
                for r in rows
            ]
