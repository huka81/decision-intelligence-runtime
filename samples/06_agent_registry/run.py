#!/usr/bin/env python3
"""
06_agent_registry - Demonstrates Agent Discovery & Metadata (DIR §2.3).

Shows:
- Registration of agents with Capability Contracts.
- Lookup of agent metadata (priority, supported policies).
- runtime inspection of active agents.
"""

import logging
from pathlib import Path
from pprint import pprint

from dir.agent_registry import AgentRegistry
from utils import ensure_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    print("=" * 70)
    print("Agent Registry Demonstration")
    print("=" * 70)

    # 1. Setup DB
    data_dir = Path(__file__).resolve().parent / "data"
    db_path = ensure_db(data_dir / "registry.db")
    print(f"Database: {db_path}")

    registry = AgentRegistry(str(db_path))

    # 2. Register Agents
    print("\n[Registration] Registering agents...")
    
    # Agent A: High priority Monitor
    registry.register_agent(
        agent_id="agent_supervisor",
        contract={
            "role": "MONITOR",
            "capabilities": ["halt_system", "audit_log"],
            "version": "1.0.0"
        },
        priority=100
    )

    # Agent B: Standard Trader
    registry.register_agent(
        agent_id="agent_trader_btc",
        contract={
            "role": "EXECUTOR",
            "capabilities": ["place_order", "cancel_order"],
            "supported_instruments": ["BTC-USD"],
            "version": "2.1.0"
        },
        priority=10
    )

    # 3. List Agents
    agents = registry.list_agents()
    print(f"\n[Discovery] Active Agents: {agents}")
    
    if "agent_supervisor" in agents and "agent_trader_btc" in agents:
         print("   ✅ Listing successful")
    else:
         print("   ❌ Listing failed")

    # 4. Inspect Metadata
    print("\n[Inspection] Checking 'agent_trader_btc'...")
    contract = registry.get_agent_contract("agent_trader_btc")
    priority = registry.get_agent_priority("agent_trader_btc")

    print(f"   Priority: {priority}")
    print("   Contract:")
    pprint(contract)

    # Verification
    if priority == 10 and contract["role"] == "EXECUTOR":
        print("\nSUCCESS: Agent registry persisted and retrieved data correctly.")
    else:
        print("\nFAILURE: Data mismatch.")


if __name__ == "__main__":
    main()
