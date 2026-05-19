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

Uses canonical ``sqlite_storage`` (full schema), ``DecisionRuntime`` handshake
so ``agent_state`` / ``flow_context`` FKs resolve, and append-only
``decision_audit`` telemetry (see ``telemetry.py``).
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

from dir_core import DecisionRuntime, new_dfid  # noqa: E402
from dir_core.storage import sqlite_storage  # noqa: E402

from telemetry import (  # noqa: E402
    record_agent_state_updated,
    record_context_session_updated,
    record_demo_end,
    record_demo_start,
    record_working_context_compiled,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    print("=" * 70)
    print("Context Store Demonstration")
    print("=" * 70)

    run_id = (
        f"sample_04_context_store_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )

    data_dir = Path(__file__).resolve().parent / "data"
    db_path = data_dir / "04_context_store.db"
    bundle = sqlite_storage(str(db_path))
    runtime = DecisionRuntime(bundle)
    store = runtime.context_store
    audit = runtime.audit

    print(f"Database: {db_path.resolve()}")

    agent_id = "agent_risk_analyzer_v1"
    contract = {
        "agent_id": agent_id,
        "role": "MONITOR",
        "mission": "Context store sample — layered session and state.",
        "allowed_policy_types": ["HOLD"],
        "authorized_instruments": ["BTC-USD", "ETH-USD"],
    }
    hr = runtime.register_agent(agent_id, contract, "1.0.0", priority=10)
    if not hr.accepted:
        print(f"\nFAILURE: Handshake rejected: {hr.reason}")
        record_demo_end(
            audit,
            run_id,
            status="error",
            details={"handshake_reason": hr.reason},
        )
        sys.exit(1)

    record_demo_start(
        audit,
        run_id,
        agent_id=agent_id,
        details={"persistence": "sqlite_storage (canonical schema)"},
    )

    flow_dfid = new_dfid()
    print(f"\n[Setup] Agent={agent_id}, flow DFID={flow_dfid}")
    print(f"         run_id={run_id}")

    print("[State] Setting authoritative state...")
    state_payload = {
        "policy_version": "2.1.0",
        "risk_threshold": 0.75,
        "allowed_markets": ["BTC-USD", "ETH-USD"],
        "last_audit": "2023-10-27",
    }
    store.update_state(agent_id, state_payload)
    record_agent_state_updated(
        audit,
        run_id,
        agent_id=agent_id,
        keys_updated=sorted(state_payload.keys()),
    )

    print("[Session] Setting ephemeral session data...")
    session_payload = {
        "request_id": "req_123",
        "user_intent": "check_risk",
        "input_payload": {"symbol": "BTC-USD", "amount": 5.0},
    }
    store.update_session(flow_dfid, session_payload, agent_id=agent_id)
    record_context_session_updated(
        audit,
        run_id,
        flow_dfid,
        agent_id=agent_id,
        keys_updated=sorted(session_payload.keys()),
    )

    print("\n[Compiler] Building Working Context...")
    ctx = store.compile_working_context(agent_id, flow_dfid)
    record_working_context_compiled(
        audit,
        run_id,
        flow_dfid,
        agent_id=agent_id,
        session_keys=len(ctx.get("session") or {}),
        state_keys=len(ctx.get("state") or {}),
    )

    print("\n" + "-" * 30)
    print("WORKING CONTEXT CONTAINS:")
    print("-" * 30)
    pprint(ctx)
    print("-" * 30)

    success = (
        ctx["state"]["risk_threshold"] == 0.75
        and ctx["session"]["user_intent"] == "check_risk"
    )
    record_demo_end(
        audit,
        run_id,
        status="ok" if success else "error",
        details={"compiled_ok": success},
    )

    if success:
        n = len(
            [
                e
                for e in audit.all_events_chronological()
                if (e.get("details") or {}).get("run_id") == run_id
            ]
        )
        print(
            "\nSUCCESS: Context compiled correctly from state and session layers."
        )
        print(f"Audit events for this run_id: {n}")
    else:
        print("\nFAILURE: Context missing expected data.")
        sys.exit(1)


if __name__ == "__main__":
    main()
