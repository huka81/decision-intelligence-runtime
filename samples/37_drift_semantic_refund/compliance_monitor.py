"""
ComplianceMonitor: rolling semantic violation rate over execution_log JOIN context_snapshots.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from dir.agent_registry import AgentRegistry

    from audit_store import AuditStore

logger = logging.getLogger(__name__)


class ComplianceMonitor:
    def __init__(
        self,
        audit: "AuditStore",
        registry: "AgentRegistry",
        *,
        agent_id: str,
        window_size: int,
        violation_rate_threshold: float,
        suspension_reason: str,
        min_delay_hours_for_refund: float,
    ) -> None:
        self._audit = audit
        self._registry = registry
        self._agent_id = agent_id
        self._window = window_size
        self._threshold = violation_rate_threshold
        self._reason = suspension_reason
        self._min_delay = min_delay_hours_for_refund

    def evaluate_after_execution(self, last_dfid: str) -> Tuple[bool, Optional[float]]:
        """
        After a successful refund execution, recompute violation rate on the last `window` refunds.

        Violation: refund executed while delay_hours <= min_delay_hours_for_refund
        (policy requires delay strictly greater than this value).

        Returns:
            (should_stop, violation_rate or None if window not full)
        """
        if self._audit.execution_count() < self._window:
            return False, None

        rate = self._audit.rolling_refund_violation_rate(
            self._window,
            min_delay_hours_exclusive=self._min_delay,
        )
        if rate is None:
            return False, None

        self._audit.record(
            last_dfid,
            "MONITOR_TICK",
            state="OK" if rate <= self._threshold + 1e-12 else "ALERT",
            details={
                "violation_rate": round(rate, 4),
                "window_size": self._window,
                "threshold": self._threshold,
                "min_delay_hours_for_refund": self._min_delay,
            },
        )

        if rate > self._threshold + 1e-12:
            self._registry.set_agent_status(self._agent_id, "SUSPENDED", self._reason)
            pct = rate * 100.0
            self._audit.record(
                last_dfid,
                "AGENT_SUSPENDED",
                state="SUSPENDED",
                details={
                    "agent_id": self._agent_id,
                    "reason": self._reason,
                    "violation_rate": round(rate, 4),
                },
            )
            logger.warning(
                "Alert: %.1f%% of recent refunds violate the 48h delay rule. Suspending agent.",
                pct,
            )
            print(
                f"Alert: {pct:.0f}% of recent refunds violate the 48h delay rule. Suspending agent."
            )
            return True, rate

        return False, rate
