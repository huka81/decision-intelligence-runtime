#!/usr/bin/env python3
"""
06_agent_registry - Demonstrates Agent Discovery & Metadata (DIR §2.3).

Shows:
- Registration of agents via canonical handshake (SemVer + session token).
- Lookup of agent metadata (priority, supported policies).
- Runtime inspection of active agents.
- Append-only decision audit for the demo run (telemetry guidelines).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from pprint import pprint

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import DecisionRuntime, new_dfid
from dir_core.storage import sqlite_storage

from telemetry import (
    record_demo_end,
    record_demo_start,
    record_handshake_accepted,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    run_id = (
        f"sample_06_agent_registry_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    print("=" * 70)
    print("Agent Registry Demonstration")
    print("=" * 70)

    data_dir = Path(__file__).resolve().parent / "data"
    db_path = data_dir / "06_agent_registry.db"
    bundle = sqlite_storage(str(db_path))
    runtime = DecisionRuntime(bundle)
    registry = runtime.registry
    audit = runtime.audit

    print(f"Database: {db_path.resolve()}")

    record_demo_start(
        audit,
        run_id,
        details={"persistence": "sqlite_storage (canonical schema)"},
    )

    print("\n[Registration] Handshake (register) agents...")

    failures: list[str] = []

    # Agent A: High priority Monitor
    sup_contract = {
        "role": "MONITOR",
        "capabilities": ["halt_system", "audit_log"],
        "version": "1.0.0",
    }
    hr = runtime.register_agent(
        "agent_supervisor",
        sup_contract,
        str(sup_contract.get("version", "1.0.0")),
        priority=100,
    )
    if not hr.accepted:
        failures.append(f"agent_supervisor: {hr.reason}")
        print(f"   [NO] supervisor handshake: {hr.reason}")
    else:
        record_handshake_accepted(
            audit,
            run_id,
            new_dfid(),
            agent_id="agent_supervisor",
            priority=100,
            agent_version=str(sup_contract.get("version", "1.0.0")),
        )
        print("   [OK] agent_supervisor handshake accepted")

    # Agent B: Standard Trader
    trader_contract = {
        "role": "EXECUTOR",
        "capabilities": ["place_order", "cancel_order"],
        "supported_instruments": ["BTC-USD"],
        "version": "1.2.0",
    }
    hr2 = runtime.register_agent(
        "agent_trader_btc",
        trader_contract,
        str(trader_contract.get("version", "1.0.0")),
        priority=10,
    )
    if not hr2.accepted:
        failures.append(f"agent_trader_btc: {hr2.reason}")
        print(f"   [NO] trader handshake: {hr2.reason}")
    else:
        record_handshake_accepted(
            audit,
            run_id,
            new_dfid(),
            agent_id="agent_trader_btc",
            priority=10,
            agent_version=str(trader_contract.get("version", "1.0.0")),
        )
        print("   [OK] agent_trader_btc handshake accepted")

    # 3. List Agents
    agents = registry.list_agents()
    print(f"\n[Discovery] Active Agents: {agents}")

    if "agent_supervisor" in agents and "agent_trader_btc" in agents:
        print("   [OK] Listing successful")
    else:
        print("   [NO] Listing failed")

    # 4. Inspect Metadata
    print("\n[Inspection] Checking 'agent_trader_btc'...")
    contract = registry.get_agent_contract("agent_trader_btc")
    priority = registry.get_agent_priority("agent_trader_btc")

    print(f"   Priority: {priority}")
    print("   Contract:")
    pprint(contract)

    success = (
        not failures
        and priority == 10
        and bool(contract)
        and contract.get("role") == "EXECUTOR"
    )

    end_details: dict = {"failures": failures} if failures else {"agents_registered": 2}
    record_demo_end(
        audit,
        run_id,
        status="ok" if success else "error",
        details=end_details,
    )

    if success:
        print("\nSUCCESS: Agent registry persisted and retrieved data correctly.")
        n_audit = len(
            [
                e
                for e in audit.all_events_chronological()
                if (e.get("details") or {}).get("run_id") == run_id
            ]
        )
        print(f"Audit events for this run (run_id / correlation_id): {n_audit}")
    else:
        print("\nFAILURE: Data mismatch or handshake rejected.")
        sys.exit(1)


if __name__ == "__main__":
    main()
