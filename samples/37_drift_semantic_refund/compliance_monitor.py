"""
ComplianceMonitor: rolling semantic violation rate over ``REFUND_EXECUTED`` audit rows
for this ``simulation_id`` (canonical ``decision_audit``).
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


def executed_delay_hours_for_simulation(
    bundle: StorageBundle,
    simulation_id: str,
) -> List[float]:
    out: List[float] = []
    for row in bundle.decision_audit.all_events_chronological():
        if row.get("event") != "REFUND_EXECUTED":
            continue
        details = row.get("details") or {}
        if details.get("simulation_id") != simulation_id:
            continue
        out.append(float(details.get("delay_hours", 0.0)))
    return out


class ComplianceMonitor:
    def __init__(
        self,
        bundle: StorageBundle,
        registry: "AgentRegistry",
        *,
        simulation_id: str,
        agent_id: str,
        window_size: int,
        violation_rate_threshold: float,
        suspension_reason: str,
        min_delay_hours_for_refund: float,
    ) -> None:
        self._bundle = bundle
        self._registry = registry
        self._simulation_id = simulation_id
        self._agent_id = agent_id
        self._window = window_size
        self._threshold = violation_rate_threshold
        self._reason = suspension_reason
        self._min_delay = min_delay_hours_for_refund

    def execution_count(self) -> int:
        return len(executed_delay_hours_for_simulation(self._bundle, self._simulation_id))

    def evaluate_after_execution(self, last_dfid: str) -> Tuple[bool, Optional[float]]:
        delays = executed_delay_hours_for_simulation(self._bundle, self._simulation_id)
        if len(delays) < self._window:
            return False, None

        window_delays = delays[-self._window :]
        viol = sum(
            1 for dh in window_delays if float(dh) <= self._min_delay + 1e-9
        )
        rate = viol / float(self._window)

        state = "OK" if rate <= self._threshold + 1e-12 else "ALERT"
        record_monitor_tick(
            self._bundle,
            last_dfid,
            self._simulation_id,
            agent_id=self._agent_id,
            state=state,
            violation_rate=rate,
            window_size=self._window,
            threshold=self._threshold,
            min_delay_hours_for_refund=self._min_delay,
        )

        if rate > self._threshold + 1e-12:
            self._registry.set_agent_status(self._agent_id, "SUSPENDED", self._reason)
            record_agent_suspended(
                self._bundle,
                last_dfid,
                self._simulation_id,
                agent_id=self._agent_id,
                reason=self._reason,
                violation_rate=rate,
            )
            pct = rate * 100.0
            log_with_dfid(
                logger,
                last_dfid,
                logging.WARNING,
                "Alert: %.1f%% of recent refunds violate the delay rule. Suspending agent.",
                pct,
            )
            return True, rate

        return False, rate
