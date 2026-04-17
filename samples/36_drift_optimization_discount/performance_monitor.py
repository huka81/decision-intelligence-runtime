"""
PerformanceMonitor: rolling average discount over executed retention steps
(read from canonical ``decision_audit`` events for this ``simulation_id``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from dir_core.storage import StorageBundle
from dir_core.utils.logging_utils import log_with_dfid

from telemetry import record_agent_suspended, record_monitor_tick

if TYPE_CHECKING:
    from dir_core.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


def executed_discounts_for_simulation(
    bundle: StorageBundle,
    simulation_id: str,
) -> List[float]:
    out: List[float] = []
    for row in bundle.decision_audit.all_events_chronological():
        if row.get("event") != "RETENTION_EXECUTED":
            continue
        details = row.get("details") or {}
        if details.get("simulation_id") != simulation_id:
            continue
        out.append(float(details.get("discount_offered", 0.0)))
    return out


class PerformanceMonitor:
    def __init__(
        self,
        bundle: StorageBundle,
        registry: "AgentRegistry",
        *,
        simulation_id: str,
        agent_id: str,
        window_size: int,
        avg_threshold_pct: float,
        suspension_reason: str,
    ) -> None:
        self._bundle = bundle
        self._registry = registry
        self._simulation_id = simulation_id
        self._agent_id = agent_id
        self._window = window_size
        self._threshold = avg_threshold_pct
        self._reason = suspension_reason

    def execution_count(self) -> int:
        return len(executed_discounts_for_simulation(self._bundle, self._simulation_id))

    def evaluate_after_execution(self, last_dfid: str) -> Tuple[bool, Optional[float]]:
        discounts = executed_discounts_for_simulation(self._bundle, self._simulation_id)
        if len(discounts) < self._window:
            return False, None

        avg = sum(discounts[-self._window :]) / float(self._window)

        state = "OK" if avg <= self._threshold else "ALERT"
        record_monitor_tick(
            self._bundle,
            last_dfid,
            self._simulation_id,
            state=state,
            moving_avg_discount_pct=avg,
            window_size=self._window,
            threshold_pct=self._threshold,
        )

        if avg > self._threshold + 1e-9:
            self._registry.set_agent_status(self._agent_id, "SUSPENDED", self._reason)
            record_agent_suspended(
                self._bundle,
                last_dfid,
                self._simulation_id,
                agent_id=self._agent_id,
                reason=self._reason,
                moving_avg_discount_pct=avg,
            )
            log_with_dfid(
                logger,
                last_dfid,
                logging.WARNING,
                "Alert: Moving average discount is %.2f%%. Suspending agent.",
                avg,
            )
            return True, avg

        return False, avg
