"""
ApprovalMonitor: rolling high-risk approval rate over CREDIT_LIMIT_RAISED audit rows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from dir_core.storage import StorageBundle
from dir_core.utils.logging_utils import log_with_dfid

from schemas import is_high_risk_approval
from telemetry import record_agent_suspended, record_monitor_tick

if TYPE_CHECKING:
    from dir_core.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


def run_scoped_events(
    all_events: List[dict],
    simulation_id: str,
) -> List[dict]:
    """Audit rows for the latest simulation run (last START … matching END)."""
    start_idx = None
    for i in range(len(all_events) - 1, -1, -1):
        e = all_events[i]
        if e.get("event") != "SIMULATION_START":
            continue
        d = e.get("details") or {}
        if d.get("simulation_id") == simulation_id:
            start_idx = i
            break
    if start_idx is None:
        return []
    out: List[dict] = []
    for j in range(start_idx, len(all_events)):
        e = all_events[j]
        if e.get("event") in ("SIMULATION_START", "SIMULATION_END"):
            continue
        out.append(e)
        if e.get("event") == "SIMULATION_END":
            d = e.get("details") or {}
            if d.get("simulation_id") == simulation_id:
                break
    return out


def is_drift_batch_execution(details: dict) -> bool:
    label = str(details.get("scenario_label", ""))
    customer_id = str(details.get("customer_id", ""))
    return label.startswith("drift_") or customer_id.startswith("drift_cust_")


def drift_raise_events(
    all_events: List[dict],
    simulation_id: str,
) -> List[dict]:
    """CREDIT_LIMIT_RAISED rows from Phase B drift batch in the current run."""
    out: List[dict] = []
    for row in run_scoped_events(all_events, simulation_id):
        if row.get("event") != "CREDIT_LIMIT_RAISED":
            continue
        details = row.get("details") or {}
        if not is_drift_batch_execution(details):
            continue
        out.append(row)
    return out


def high_risk_flags_for_drift_run(
    bundle: StorageBundle,
    simulation_id: str,
) -> List[bool]:
    flags: List[bool] = []
    for row in drift_raise_events(
        bundle.decision_audit.all_events_chronological(),
        simulation_id,
    ):
        details = row.get("details") or {}
        flags.append(bool(details.get("high_risk", False)))
    return flags


def drift_raise_labels_for_window(
    bundle: StorageBundle,
    simulation_id: str,
    window_size: int,
) -> Tuple[List[str], List[bool]]:
    rows = drift_raise_events(
        bundle.decision_audit.all_events_chronological(),
        simulation_id,
    )
    labels: List[str] = []
    flags: List[bool] = []
    for row in rows:
        details = row.get("details") or {}
        labels.append(str(details.get("scenario_label", details.get("customer_id", "?"))))
        flags.append(bool(details.get("high_risk", False)))
    return labels[-window_size:], flags[-window_size:]


class ApprovalMonitor:
    def __init__(
        self,
        bundle: StorageBundle,
        registry: "AgentRegistry",
        *,
        simulation_id: str,
        agent_id: str,
        window_size: int,
        threshold: float,
        suspension_reason: str,
        min_income_to_limit_ratio: float,
    ) -> None:
        self._bundle = bundle
        self._registry = registry
        self._simulation_id = simulation_id
        self._agent_id = agent_id
        self._window = window_size
        self._threshold = threshold
        self._reason = suspension_reason
        self._min_ratio = min_income_to_limit_ratio

    def execution_count(self) -> int:
        return len(high_risk_flags_for_drift_run(self._bundle, self._simulation_id))

    def evaluate_after_execution(self, last_dfid: str) -> Tuple[bool, Optional[float]]:
        flags = high_risk_flags_for_drift_run(self._bundle, self._simulation_id)
        if len(flags) < self._window:
            return False, None

        window_flags = flags[-self._window :]
        window_labels, _ = drift_raise_labels_for_window(
            self._bundle,
            self._simulation_id,
            self._window,
        )
        high_risk_count = sum(1 for f in window_flags if f)
        rate = high_risk_count / float(self._window)

        state = "OK" if rate <= self._threshold + 1e-12 else "ALERT"
        record_monitor_tick(
            self._bundle,
            last_dfid,
            self._simulation_id,
            agent_id=self._agent_id,
            state=state,
            high_risk_rate=rate,
            window_size=self._window,
            threshold=self._threshold,
            high_risk_count=high_risk_count,
            window_high_risk_flags=window_flags,
            window_labels=window_labels,
            drift_executions_total=len(flags),
        )

        if rate > self._threshold + 1e-12:
            self._registry.set_agent_status(self._agent_id, "SUSPENDED", self._reason)
            record_agent_suspended(
                self._bundle,
                last_dfid,
                self._simulation_id,
                agent_id=self._agent_id,
                reason=self._reason,
                high_risk_rate=rate,
            )
            log_with_dfid(
                logger,
                last_dfid,
                logging.WARNING,
                "Approval rate drift: %.1f%% high-risk in window — agent SUSPENDED",
                rate * 100.0,
            )
            return True, rate

        return False, rate

    @staticmethod
    def compute_high_risk(
        declared_income_pln: float,
        requested_limit_pln: float,
        min_income_to_limit_ratio: float,
    ) -> bool:
        return is_high_risk_approval(
            declared_income_pln,
            requested_limit_pln,
            min_income_to_limit_ratio,
        )
