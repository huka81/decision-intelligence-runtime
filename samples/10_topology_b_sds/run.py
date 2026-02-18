#!/usr/bin/env python3
"""
10_topology_b_sds - Structural Decision Stream (SDS).

DIR §2.4 / Topologies B.
High-Velocity processing where "Structure is Safety".
Key features:
1. Strict Grammar/Schema enforcement (Pydantic validation) as the first line of defense.
2. JIT Drift Check (monitoring distribution of decisions).
3. Batched execution for throughput.

Scenario: A high-frequency trading or ad-bidding agent that must adhere to strict formats.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic import BaseModel, ValidationError

# Using DIM for final policy check
from dir.dim import validate_proposal
from dir.models import PolicyProposal
from dir import new_dfid

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# --- 1. Transmission Schema (The "Grammar") ---

class BidRequest(BaseModel):
    request_id: str
    item_id: str
    base_price: float
    user_segment: str

class BidResponse(BaseModel):
    # Strict structure required by the exchange
    request_id: str
    bid_price: float
    currency: str = "USD"
    creative_id: str


# --- 2. JIT Drift Monitor ---

@dataclass
class DriftMonitor:
    window_size: int = 100
    history: List[float] = field(default_factory=list)
    mean_threshold: float = 50.0  # Alert if mean bid > 50

    def record(self, value: float) -> bool:
        self.history.append(value)
        if len(self.history) > self.window_size:
            self.history.pop(0)
        
        if len(self.history) >= 10:
            avg = sum(self.history) / len(self.history)
            if avg > self.mean_threshold:
                return False  # Drift detected!
        return True


# --- 3. The Structural Agent ---

class StructuralAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.drift_monitor = DriftMonitor()

    def process_batch(self, requests: List[dict]) -> None:
        logger.info(f"Processing batch of {len(requests)} requests...")
        
        for raw_req in requests:
            # Step A: Structural Validation (The "Grammar" Check)
            try:
                req = BidRequest(**raw_req)
            except ValidationError as e:
                logger.error(f"❌ INVALID STRUCTURE: {e}")
                continue

            # Step B: Logic / Strategy
            # Simple strategy: bid 10% above base, unless segment is "premium"
            multiplier = 1.5 if req.user_segment == "premium" else 1.1
            bid_price = round(req.base_price * multiplier, 2)
            
            # Step C: JIT Drift Check
            if not self.drift_monitor.record(bid_price):
                logger.warning(f"⚠️ DRIFT DETECTED! High bid average. Skipping {req.request_id}.")
                continue

            # Step D: Response Formatting
            resp = BidResponse(
                request_id=req.request_id,
                bid_price=bid_price,
                creative_id="cr_123"
            )

            # Step E: DIM Validation (Final Guardrail)
            # Create PolicyProposal for the runtime to approve
            proposal = PolicyProposal(
                dfid=new_dfid(), # New flow for this micro-decision
                agent_id=self.agent_id,
                policy_kind="SUBMIT_BID",
                params=resp.model_dump(),
                confidence=0.95
            )

            # Check with DIM (Dummy RBAC context)
            verdict, reason = validate_proposal(proposal, context={"state": {"risk_score": 0.0}})
            
            if verdict == "ACCEPT":
                 logger.info(f"✅ BID SENT: {resp.bid_price} for {req.item_id}")
            else:
                 logger.info(f"⛔ BLOCKED by DIM: {reason}")


# --- 4. Simulation ---

def main():
    agent = StructuralAgent("agent_bidder_fast")
    
    # Generate batch of traffic
    requests = []
    for i in range(10):
        requests.append({
            "request_id": f"req_{i}",
            "item_id": f"item_{random.randint(100, 999)}",
            "base_price": random.uniform(10.0, 40.0), # Normal prices
            "user_segment": random.choice(["standard", "premium"])
        })
    
    # Inject Malformed Data (Structure Breach)
    requests.append({
        "request_id": "req_malformed",
        "base_price": "NOT_A_NUMBER", # Error
        "user_segment": "standard" 
        # Missing item_id
    })

    # Inject Drift-Causing Data (High prices)
    for i in range(5):
        requests.append({
            "request_id": f"req_high_{i}",
            "item_id": "item_999",
            "base_price": 100.0, # Will trigger drift monitor (>50 avg)
            "user_segment": "premium"
        })

    agent.process_batch(requests)


if __name__ == "__main__":
    main()
