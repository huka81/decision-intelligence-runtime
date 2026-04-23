#!/usr/bin/env python3
"""
04_context_store - Demonstrates Layered Context Management (DIR §8).

Layers:
- Session: Ephemeral data linked to the current DecisionFlow (dfid).
- State: Long-lived authoritative data linked to the Agent (agent_id).
- Memory: Long-term (stub in MVP).
- Artifacts: Reference (stub in MVP).

Shows how `compile_working_context` merges these into a single view for
the decision-making process. This sample demonstrates Session and State
layers; Memory and Artifacts are stubs per MVP.
"""

import json
import logging
from pathlib import Path
from pprint import pprint

from dir_core import new_dfid
from dir_core.storage import ensure_db
from dir_core.context_store import ContextStore

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    print("=" * 70)
    print("Context Store Demonstration")
    print("=" * 70)

    # 1. Setup DB
    data_dir = Path(__file__).resolve().parent / "data"
    db_path = ensure_db(data_dir / "context.db")
    print(f"Database: {db_path}")

    store = ContextStore(str(db_path))

    # 2. Define Agent and Flow
    agent_id = "agent_risk_analyzer_v1"
    dfid = new_dfid()
    
    print(f"\n[Setup] Agent={agent_id}, DFID={dfid}")

    # 3. Populate Authoritative STATE (Long-term)
    # E.g. User preferences, policy versions, historical metrics.
    print("[State] Setting authoritative state...")
    store.update_state(agent_id, {
        "policy_version": "2.1.0",
        "risk_threshold": 0.75,
        "allowed_markets": ["BTC-USD", "ETH-USD"],
        "last_audit": "2023-10-27"
    })
    
    # 4. Populate Ephemeral SESSION (Current Flow)
    # E.g. Incoming request params, intermediate reasoning steps.
    print("[Session] Setting ephemeral session data...")
    store.update_session(dfid, {
        "request_id": "req_123",
        "user_intent": "check_risk",
        "input_payload": {"symbol": "BTC-USD", "amount": 5.0}
    })

    # 5. Compile Working Context
    # This is what the Agent receives to make a decision.
    print("\n[Compiler] Building Working Context...")
    ctx = store.compile_working_context(agent_id, dfid)
    
    print("\n" + "-" * 30)
    print("WORKING CONTEXT CONTAINS:")
    print("-" * 30)
    pprint(ctx)
    print("-" * 30)

    # Verification
    if ctx["state"]["risk_threshold"] == 0.75 and ctx["session"]["user_intent"] == "check_risk":
        print("\nSUCCESS: Context compiled correctly from state and session layers.")
    else:
        print("\nFAILURE: Context missing expected data.")


if __name__ == "__main__":
    main()

