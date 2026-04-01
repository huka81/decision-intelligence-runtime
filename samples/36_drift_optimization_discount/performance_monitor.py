"""
PerformanceMonitor: rolling average discount over execution_log JOIN decision_flows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from dir.agent_registry import AgentRegistry

    from audit_store import AuditStore

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    def __init__(
        self,
        audit: "AuditStore",
        registry: "AgentRegistry",
        *,
        agent_id: str,
        window_size: int,
        avg_threshold_pct: float,
        suspension_reason: str,
    ) -> None:
        self._audit = audit
        self._registry = registry
        self._agent_id = agent_id
        self._window = window_size
        self._threshold = avg_threshold_pct
        self._reason = suspension_reason

    def evaluate_after_execution(self, last_dfid: str) -> Tuple[bool, Optional[float]]:
        """
        After a successful execution, recompute rolling average.

        Returns:
            (should_stop, moving_average_pct or None if window not full)
        """
        if self._audit.execution_count() < self._window:
            return False, None

        avg = self._audit.rolling_avg_discount_joined(self._window)
        if avg is None:
            return False, None

        self._audit.record(
            last_dfid,
            "MONITOR_TICK",
            state="OK" if avg <= self._threshold else "ALERT",
            details={
                "moving_avg_discount_pct": round(avg, 4),
                "window_size": self._window,
                "threshold_pct": self._threshold,
            },
        )

        if avg > self._threshold + 1e-9:
            self._registry.set_agent_status(self._agent_id, "SUSPENDED", self._reason)
            self._audit.record(
                last_dfid,
                "AGENT_SUSPENDED",
                state="SUSPENDED",
                details={
                    "agent_id": self._agent_id,
                    "reason": self._reason,
                    "moving_avg_discount_pct": round(avg, 4),
                },
            )
            logger.warning(
                "Alert: Moving average discount is %.2f%%. Suspending agent.",
                avg,
            )
            return True, avg

        return False, avg
