#!/usr/bin/env python3
"""
10_topology_b_sds — Technical minimal demo: Topology B (SDS).

Focus: Pydantic input grammar, drift window heuristic, ``BidResponse`` shape,
DIM via ``DecisionRuntime.evaluate_proposal`` (default in-memory audit).

Aligned with ``06-technical-sample-development-guide.mdc``: no ``samples/shared``,
no YAML, ``memory_storage`` + ``DecisionRuntime`` only.

Run: python samples/10_topology_b_sds/run.py
"""
from __future__ import annotations

import logging
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import (  # noqa: E402
    DecisionRuntime,
    PolicyProposal,
    ResponsibilityContract,
    new_dfid,
)
from dir_core.data_types import ContractRole, ValidationVerdict  # noqa: E402
from dir_core.storage import memory_storage  # noqa: E402
from dir_core.utils.logging_utils import log_with_dfid  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SEED = 42
_AGENT_ID = "agent_bidder_fast"


class BidRequest(BaseModel):
    request_id: str
    item_id: str
    base_price: float
    user_segment: str


class BidResponse(BaseModel):
    request_id: str
    bid_price: float
    currency: str = "USD"
    creative_id: str


@dataclass
class DriftMonitor:
    window_size: int = 100
    history: List[float] = field(default_factory=list)
    mean_threshold: float = 50.0

    def record(self, value: float) -> bool:
        self.history.append(value)
        if len(self.history) > self.window_size:
            self.history.pop(0)
        if len(self.history) >= 10:
            avg = sum(self.history) / len(self.history)
            if avg > self.mean_threshold:
                return False
        return True


def _contract_dict() -> Dict[str, Any]:
    return ResponsibilityContract(
        agent_id=_AGENT_ID,
        role=ContractRole.EXECUTOR,
        mission="Submit exchange-compatible bids under SDS structural rules.",
        authorized_instruments=["ADS"],
        allowed_policy_types=["SUBMIT_BID"],
        escalate_on_uncertainty=0.7,
        max_drawdown_limit=0.05,
        wake_up_threshold_pct=0.5,
        parent_agent_id=None,
    ).model_dump()


class StructuralAgent:
    """Schema, strategy, drift window, then ``PolicyProposal`` + DIM."""

    def __init__(self, agent_id: str, runtime: DecisionRuntime) -> None:
        self.agent_id = agent_id
        self.runtime = runtime
        self.drift_monitor = DriftMonitor()

    def process_batch(self, requests: List[Dict[str, Any]]) -> Dict[str, int]:
        batch_dfid = new_dfid()
        log_with_dfid(
            logger,
            batch_dfid,
            logging.INFO,
            "SDS: processing batch of %d requests",
            len(requests),
        )
        stats = {
            "struct_invalid": 0,
            "drift_skip": 0,
            "dim_accept": 0,
            "dim_reject": 0,
        }

        for raw_req in requests:
            try:
                req = BidRequest(**raw_req)
            except ValidationError as e:
                stats["struct_invalid"] += 1
                log_with_dfid(
                    logger,
                    batch_dfid,
                    logging.WARNING,
                    "INVALID_STRUCTURE skipped: %s",
                    e,
                )
                continue

            multiplier = 1.5 if req.user_segment == "premium" else 1.1
            bid_price = round(req.base_price * multiplier, 2)

            if not self.drift_monitor.record(bid_price):
                stats["drift_skip"] += 1
                log_with_dfid(
                    logger,
                    batch_dfid,
                    logging.WARNING,
                    "DRIFT_DETECTED skipping request_id=%s",
                    req.request_id,
                )
                continue

            resp = BidResponse(
                request_id=req.request_id,
                bid_price=bid_price,
                creative_id="cr_123",
            )
            dfid = new_dfid()
            proposal = PolicyProposal(
                dfid=dfid,
                agent_id=self.agent_id,
                policy_kind="SUBMIT_BID",
                params=resp.model_dump(),
                confidence=0.95,
                justification="Structural bid from SDS demo agent.",
            )
            verdict, reason = self.runtime.evaluate_proposal(
                proposal,
                {},
                dim_context={"state": {"risk_score": 0.0}},
                allowed_agents=[self.agent_id],
            )
            if verdict == ValidationVerdict.ACCEPT:
                stats["dim_accept"] += 1
                log_with_dfid(
                    logger,
                    dfid,
                    logging.INFO,
                    "BID_SENT bid_price=%s item_id=%s",
                    resp.bid_price,
                    req.item_id,
                )
            else:
                stats["dim_reject"] += 1
                log_with_dfid(
                    logger,
                    dfid,
                    logging.INFO,
                    "BLOCKED_BY_DIM reason=%s",
                    reason,
                )

        return stats


def _build_demo_batch(rng: random.Random) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(10):
        out.append(
            {
                "request_id": f"req_{i}",
                "item_id": f"item_{rng.randint(100, 999)}",
                "base_price": round(rng.uniform(10.0, 40.0), 2),
                "user_segment": rng.choice(["standard", "premium"]),
            }
        )
    out.append(
        {
            "request_id": "req_malformed",
            "base_price": "NOT_A_NUMBER",
            "user_segment": "standard",
        }
    )
    for i in range(5):
        out.append(
            {
                "request_id": f"req_high_{i}",
                "item_id": "item_999",
                "base_price": 100.0,
                "user_segment": "premium",
            }
        )
    return out


def main() -> None:
    bundle = memory_storage()
    runtime = DecisionRuntime(bundle)
    hr = runtime.register_agent(
        _AGENT_ID,
        _contract_dict(),
        agent_version="1.0.0",
    )
    if not hr.accepted:
        logger.error("Handshake rejected: %s", hr.reason)
        return

    rng = random.Random(_SEED)
    requests = _build_demo_batch(rng)
    agent = StructuralAgent(_AGENT_ID, runtime)
    stats = agent.process_batch(requests)

    print(
        f"\n[SUMMARY] struct_invalid={stats['struct_invalid']} "
        f"drift_skip={stats['drift_skip']} dim_accept={stats['dim_accept']} "
        f"dim_reject={stats['dim_reject']}",
    )


if __name__ == "__main__":
    main()
