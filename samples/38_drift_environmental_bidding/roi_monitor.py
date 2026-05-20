"""
BusinessROIMonitor: rolling CPC vs LTV; suspend after negative ROI streak.

Reads ``CPC_BID_EXECUTED`` from decision_audit for ``simulation_id``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from dir_core.storage.base import AuditStore
from dir_core.utils.logging_utils import log_with_dfid

from telemetry import (
    record_agent_suspended,
    record_monitor_tick,
    rolling_cpc_stats,
)

if TYPE_CHECKING:
    from dir_core.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class BusinessROIMonitor:
    def __init__(
        self,
        audit: AuditStore,
        registry: "AgentRegistry",
        *,
        simulation_id: str,
        agent_id: str,
        window_size: int,
        ltv_usd: float,
        negative_roi_consecutive_cycles: int,
        suspension_reason: str,
    ) -> None:
        self._audit = audit
        self._registry = registry
        self._simulation_id = simulation_id
        self._agent_id = agent_id
        self._window = window_size
        self._ltv = float(ltv_usd)
        self._need_consecutive = int(negative_roi_consecutive_cycles)
        self._reason = suspension_reason
        self._consecutive_negative = 0

    def evaluate_after_execution(
        self, last_dfid: str
    ) -> Tuple[bool, Optional[float]]:
        stats = rolling_cpc_stats(self._audit, self._simulation_id, self._window)
        if stats is None:
            return False, None

        avg_cpc, avg_market = stats
        roi = self._ltv - avg_cpc

        if roi < 0:
            self._consecutive_negative += 1
            record_monitor_tick(
                self._audit,
                last_dfid,
                self._simulation_id,
                state="ALERT",
                agent_id=self._agent_id,
                details={
                    "avg_cpc_bid_usd": round(avg_cpc, 4),
                    "avg_market_cpc_to_win_usd": round(avg_market, 4),
                    "bid_market_spread_usd": round(avg_cpc - avg_market, 4),
                    "ltv_usd": self._ltv,
                    "roi_estimate": round(roi, 4),
                    "consecutive_negative_roi_cycles": (
                        self._consecutive_negative
                    ),
                    "window_size": self._window,
                },
                causation_id=last_dfid,
            )
            log_with_dfid(
                logger,
                last_dfid,
                logging.WARNING,
                "ROI negative for %s consecutive cycles "
                "(avg bid %.2f USD, avg market floor %.2f USD, LTV %.2f USD)",
                self._consecutive_negative,
                avg_cpc,
                avg_market,
                self._ltv,
            )

            if self._consecutive_negative >= self._need_consecutive:
                self._registry.set_agent_status(
                    self._agent_id, "SUSPENDED", self._reason
                )
                record_agent_suspended(
                    self._audit,
                    last_dfid,
                    self._simulation_id,
                    agent_id=self._agent_id,
                    reason=self._reason,
                    details={
                        "avg_cpc_bid_usd": round(avg_cpc, 4),
                        "avg_market_cpc_to_win_usd": round(avg_market, 4),
                        "ltv_usd": self._ltv,
                    },
                    causation_id=last_dfid,
                )
                msg = (
                    f"Alert: CAC exceeds LTV for {self._need_consecutive} "
                    "consecutive cycles. Agent actions are no longer profitable "
                    "due to market drift. Suspending agent."
                )
                logger.warning(msg)
                log_with_dfid(logger, last_dfid, logging.WARNING, "%s", msg)
                return True, avg_cpc

            return False, avg_cpc

        self._consecutive_negative = 0
        record_monitor_tick(
            self._audit,
            last_dfid,
            self._simulation_id,
            state="OK",
            agent_id=self._agent_id,
            details={
                "avg_cpc_bid_usd": round(avg_cpc, 4),
                "avg_market_cpc_to_win_usd": round(avg_market, 4),
                "bid_market_spread_usd": round(avg_cpc - avg_market, 4),
                "ltv_usd": self._ltv,
                "roi_estimate": round(roi, 4),
                "window_size": self._window,
            },
            causation_id=last_dfid,
        )
        return False, avg_cpc
