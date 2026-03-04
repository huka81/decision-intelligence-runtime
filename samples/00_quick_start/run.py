#!/usr/bin/env python3
"""
00_quick_start - DIR Quick Start / High-Level Overview.

Demonstrates the full architecture (Figure 1):
- User Space: AI Agent (mock, simulates parsing error)
- DIR Kernel: Context Compiler, DIM, Execution Orchestrator, Context Store, Agent Registry
- External: Mock Web Sources (with prompt injection), Mock API

Scenario "Comma Catastrophe": Agent misparses 15.500/15,500 -> proposes BUY 15500 ETH.
DIR rejects: order value exceeds max_order_usd limit. No API call.

Run from repo root: python samples/00_quick_start/run.py
Requires: pip install -e .  and  pip install pyyaml
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

from dir import (
    ContextStore,
    PolicyProposal,
    new_dfid,
    validate_proposal,
)
from dir.agent_registry import AgentRegistry
from utils import ensure_db
from utils.config_loader import load_yaml_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock Web Source (with prompt injection / ambiguous number)
# ---------------------------------------------------------------------------

def mock_fetch_market_data(config: Dict[str, Any], inject_prompt: bool = True) -> Dict[str, Any]:
    """
    Simulates fetching data from external web source.
    Contains prompt injection and ambiguous locale number (15,500 vs 15.500).
    """
    mock = config.get("mock_web", {})
    prices = mock.get("prices", {"ETH-USD": 2500.0, "BTC-USD": 50000.0})
    scenario = mock.get("inject", {}) if inject_prompt else mock.get("clean", {})
    return {
        "source": "market_signal_feed",
        "suggested_position_eth": scenario.get("suggested_position_eth", "0"),
        "note": scenario.get("note", ""),
        "price_eth_usd": prices.get("ETH-USD", 2500.0),
        "price_btc_usd": prices.get("BTC-USD", 50000.0),
    }


# ---------------------------------------------------------------------------
# Mock Agent (simulates parsing error / prompt injection following)
# ---------------------------------------------------------------------------

def mock_agent_reason(
    context: Dict[str, Any],
    config: Dict[str, Any],
    simulate_error: bool = True,
) -> PolicyProposal:
    """
    Simulates AI agent reasoning. When simulate_error=True, misparses "15,500"
    as 15500 (integer) instead of 15.5, or follows prompt injection.
    """
    web = context.get("web", {})
    raw = web.get("suggested_position_eth", "0")
    prices = config.get("mock_web", {}).get("prices", {"ETH-USD": 2500.0})
    price_eth = prices.get("ETH-USD", 2500.0)

    if simulate_error:
        quantity = 15500.0
        justification = "Parsed suggested_position_eth as 15500 (locale/parsing error or injection)"
    else:
        quantity = float(raw.replace(",", "."))
        justification = "Normal interpretation of market signal"

    return PolicyProposal(
        dfid=context["meta"]["dfid"],
        agent_id=context["meta"]["agent_id"],
        policy_kind="BUY",
        params={
            "instrument": "ETH-USD",
            "quantity": quantity,
            "execution_type": "MARKET",
        },
        justification=justification,
        confidence=0.92,
    )


# ---------------------------------------------------------------------------
# Contract validation (extends DIM for order size limit)
# ---------------------------------------------------------------------------

def validate_order_against_contract(
    proposal: PolicyProposal,
    contract: Dict[str, Any],
    config: Dict[str, Any],
) -> Tuple[bool, str]:
    """Check order value against max_order_size_usd. Returns (ok, reason)."""
    if proposal.policy_kind not in ("BUY", "SELL", "PLACE_ORDER"):
        return True, "OK"
    params = proposal.params
    quantity = params.get("quantity") or 0
    instrument = params.get("instrument", "")
    prices = config.get("mock_web", {}).get("prices", {"ETH-USD": 2500.0, "BTC-USD": 50000.0})
    price = prices.get(instrument, prices.get("ETH-USD", 2500.0))
    value_usd = quantity * price
    perms = contract.get("permissions", contract)
    max_usd = perms.get("max_order_size_usd", float("inf"))
    if value_usd > max_usd:
        return False, (
            f"ORDER_VALUE_EXCEEDED: Request ~{value_usd:,.0f} USD exceeds limit {max_usd:,.0f} USD "
            f"(quantity={quantity}, instrument={instrument})"
        )
    return True, "OK"


# ---------------------------------------------------------------------------
# Mock External API
# ---------------------------------------------------------------------------

def mock_exchange_api(proposal: PolicyProposal) -> str:
    """Simulates external exchange API. Only logs; no real call."""
    params = proposal.params
    logger.info(
        "[MOCK API] Would execute: %s %s %s @ %s",
        proposal.policy_kind,
        params.get("quantity"),
        params.get("instrument"),
        params.get("execution_type"),
    )
    return "mock_receipt_" + hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Context Compiler (assembles context for Agent)
# ---------------------------------------------------------------------------

def compile_context(
    store: ContextStore,
    registry: AgentRegistry,
    agent_id: str,
    dfid: str,
    web_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Context Compiler: merges session, state, web data; fetches schema from registry."""
    store.update_session(dfid, {"web_raw": web_data})
    ctx = store.compile_working_context(agent_id, dfid)
    ctx["web"] = web_data
    ctx["meta"]["dfid"] = dfid
    ctx["meta"]["agent_id"] = agent_id
    schema = registry.get_schema(agent_id)
    if schema:
        ctx["meta"]["schema"] = schema
    return ctx


# ---------------------------------------------------------------------------
# Execution Orchestrator (when DIM accepts)
# ---------------------------------------------------------------------------

def execute_and_audit(
    proposal: PolicyProposal,
    store: ContextStore,
    dfid: str,
) -> str:
    """Execute via mock API and audit to Context Store."""
    receipt = mock_exchange_api(proposal)
    store.update_session(dfid, {
        "audit": {
            "executed": True,
            "receipt": receipt,
            "policy_kind": proposal.policy_kind,
            "params": proposal.params,
        },
    })
    return receipt


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)

    contract = config.get("contract", {})
    agent_id = contract.get("agent_id", "crypto_position_manager_01")
    agent_version = contract.get("version", "1.2.0")

    data_dir = sample_dir / "data"
    db_path = ensure_db(data_dir / "quick_start.db")
    store = ContextStore(str(db_path))
    registry = AgentRegistry(str(db_path), supported_versions="1.x")

    dfid = new_dfid()

    print("=" * 80)
    print("00_quick_start - DIR Quick Start (High-Level Overview)")
    print("=" * 80)

    # 1. Agent Registry: handshake with contract
    hr = registry.handshake(
        agent_id,
        contract,
        agent_version=agent_version,
    )
    if not hr.accepted:
        print(f"FATAL: Agent handshake failed: {hr.reason}")
        return
    print(f"\n[1] Agent Registry: Handshake accepted (agent_id={agent_id})")

    # 2. Context Compiler: fetch from mock web
    web_data = mock_fetch_market_data(config, inject_prompt=True)
    print(f"\n[2] Context Compiler: Fetching from mock web source...")
    print(f"    Web data (raw): {json.dumps(web_data, indent=2)}")
    context = compile_context(store, registry, agent_id, dfid, web_data)

    # 3. Agent: reason over context (simulates parsing error)
    proposal = mock_agent_reason(context, config, simulate_error=True)
    print(f"\n[3] Agent (Mock): Reasoning over context...")
    print(f"    Proposal: {proposal.policy_kind} {proposal.params.get('quantity')} "
          f"{proposal.params.get('instrument')} (INTERPRETATION ERROR)")
    print(f"    Justification: {(proposal.justification or '')[:60]}...")

    # 4. DIM Validation
    perms = contract.get("permissions", {})
    print(f"\n[4] DIM Validation: Checking against contract...")
    print(f"    Contract: max_order_usd={perms.get('max_order_size_usd')}, "
          f"allowed_instruments={perms.get('allowed_instruments')}")
    base_ctx = {"state": {}, "meta": context.get("meta", {})}
    verdict, reason = validate_proposal(
        proposal,
        base_ctx,
        allowed_agents=[agent_id],
    )
    if verdict == "ACCEPT":
        ok, contract_reason = validate_order_against_contract(proposal, contract, config)
        if not ok:
            verdict = "REJECT"
            reason = contract_reason

    if verdict == "REJECT":
        print(f"    REJECT: {reason}")
        print(f"\n[5] DIR blocked catastrophic action. No API call. Escalation: Human notified.")
    else:
        print(f"    ACCEPT: {reason}")
        receipt = execute_and_audit(proposal, store, dfid)
        print(f"\n[5] Execution Orchestrator: Mock API called. Receipt: {receipt}")

    # 6. Summary
    print(f"\n[6] Summary: DFID={dfid[:8]}... verdict={verdict} reason={reason[:50]}...")
    print("=" * 80)

    # Optional: second run with correct data (ACCEPT path)
    print("\n--- BONUS: Run with correct data (no injection) ---")
    web_clean = mock_fetch_market_data(config, inject_prompt=False)
    dfid2 = new_dfid()
    context2 = compile_context(store, registry, agent_id, dfid2, web_clean)
    proposal2 = mock_agent_reason(context2, config, simulate_error=False)
    print(f"    Proposal: {proposal2.policy_kind} {proposal2.params.get('quantity')} ETH")
    verdict2, reason2 = validate_proposal(proposal2, base_ctx, allowed_agents=[agent_id])
    ok2, _ = validate_order_against_contract(proposal2, contract, config)
    if ok2 and verdict2 == "ACCEPT":
        execute_and_audit(proposal2, store, dfid2)
        print(f"    Verdict: ACCEPT - Mock executed (correct interpretation).")
    else:
        print(f"    Verdict: {verdict2} - {reason2}")
    print("=" * 80)


if __name__ == "__main__":
    main()
