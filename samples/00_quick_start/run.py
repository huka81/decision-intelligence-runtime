#!/usr/bin/env python3
"""
00_quick_start - DIR Quick Start / High-Level Overview.

Demonstrates the full architecture (Figure 1):
- User Space: AI Agent (Ollama LLM or MockLLM)
- DIR Kernel: Context Compiler, DIM, Execution Orchestrator, Context Store, Agent Registry
- External: Mock Web Sources (with prompt injection), Mock API

Scenario "Comma Catastrophe": Market feed contains ambiguous "15,500" ETH.
The agent (real or mock) interprets it as 15500 — a catastrophic quantity.
DIR rejects: order value exceeds max_order_usd limit. No API call.

LLM mode (default): real Ollama (gemma3:4b or as configured in config.yaml).
Mock mode: USE_MOCK_LLM=1 or llm_defaults.provider: mock in config.yaml.

Run from repo root: python samples/00_quick_start/run.py
Requires: pip install -e .  and  pip install pyyaml
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dir_core import (
    ContextStore,
    PolicyProposal,
    new_dfid,
    validate_proposal,
)
from dir_core.agent_registry import AgentRegistry
from utils import ensure_db
from utils.config_loader import load_yaml_config
from utils.ollama_client import LLMClient, OllamaClient, check_ollama

try:
    from .llm_client import MockLLM
except ImportError:
    from llm_client import MockLLM

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
# LLM Agent — prompt building, response parsing, reasoning
# ---------------------------------------------------------------------------

def _build_system_prompt(mission: str) -> str:
    """System prompt defining the agent's role, injected into Ollama."""
    return (
        f"{mission} "
        "Analyze the market signal feed and propose a trading action. "
        "Respond with ONLY a valid JSON object — no markdown, no explanation. "
        'Keys: policy_kind ("BUY"|"SELL"|"HOLD"), '
        'params ({instrument: str, quantity: float, execution_type: str}), '
        "justification (string), confidence (float 0-1)."
    )


def _build_prompt(web_data: Dict[str, Any], config: Dict[str, Any]) -> str:
    """Build the user prompt from current market context."""
    prices = config.get("mock_web", {}).get("prices", {})
    eth_price = prices.get("ETH-USD", web_data.get("price_eth_usd", 0))
    btc_price = prices.get("BTC-USD", web_data.get("price_btc_usd", 0))
    return (
        f"Market Signal Feed:\n"
        f'- instrument: ETH-USD\n'
        f'- suggested_position_eth: "{web_data.get("suggested_position_eth", "0")}"\n'
        f'- note: "{web_data.get("note", "")}"\n'
        f"\nCurrent prices:\n"
        f"- ETH-USD: ${eth_price:,.2f}\n"
        f"- BTC-USD: ${btc_price:,.2f}\n"
        f"\nRespond with ONLY valid JSON:\n"
        '{"policy_kind": "BUY", "params": {"instrument": "ETH-USD", "quantity": <float>, "execution_type": "MARKET"}, '
        '"justification": "<your reasoning>", "confidence": <float 0.0-1.0>}'
    )


def _parse_llm_response(raw: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM response not valid JSON: %s", raw[:200])
        return None


def agent_reason(
    context: Dict[str, Any],
    config: Dict[str, Any],
    llm: LLMClient,
) -> PolicyProposal:
    """
    Agent reasoning stage (User Space).
    Builds a prompt from context, calls the LLM, parses the response into a
    PolicyProposal.  Falls back to HOLD with confidence=0 if parsing fails.
    The agent does NOT know contract limits — it reasons purely on market data.
    """
    web = context.get("web", {})
    mission = config.get("contract", {}).get("mission", "You are a crypto trading agent.")
    prompt = _build_prompt(web, config)
    system = _build_system_prompt(mission)

    try:
        raw = llm.generate(prompt, system=system)
    except Exception as exc:
        logger.warning("LLM call failed: %s — defaulting to HOLD", exc)
        raw = ""

    parsed = _parse_llm_response(raw) if raw else None

    if parsed is None:
        return PolicyProposal(
            dfid=context["meta"]["dfid"],
            agent_id=context["meta"]["agent_id"],
            policy_kind="HOLD",
            params={"instrument": "ETH-USD", "quantity": 0.0, "execution_type": "MARKET"},
            justification="LLM response could not be parsed; defaulting to HOLD.",
            confidence=0.0,
        )

    return PolicyProposal(
        dfid=context["meta"]["dfid"],
        agent_id=context["meta"]["agent_id"],
        policy_kind=str(parsed.get("policy_kind", "HOLD")),
        params=parsed.get("params", {"instrument": "ETH-USD", "quantity": 0.0, "execution_type": "MARKET"}),
        justification=str(parsed.get("justification", "")),
        confidence=float(parsed.get("confidence", 0.0)),
    )


# ---------------------------------------------------------------------------
# LLM client factory (Ollama or MockLLM — same pattern as 32_fraud_gate)
# ---------------------------------------------------------------------------

def _build_llm(config: Dict[str, Any]) -> LLMClient:
    """Build LLM client from config. Falls back to MockLLM automatically."""
    llm_cfg = config.get("llm_defaults", {})

    if os.getenv("USE_MOCK_LLM", "").strip() in ("1", "true", "yes"):
        logger.info("[LLM] Using MockLLM (USE_MOCK_LLM=1)")
        return MockLLM()

    if not llm_cfg or str(llm_cfg.get("provider", "")).lower() == "mock":
        logger.info("[LLM] Using MockLLM (provider=mock or llm_defaults absent)")
        return MockLLM()

    model = os.getenv("OLLAMA_MODEL", llm_cfg.get("model", "gemma3:4b"))
    base_url = os.getenv("OLLAMA_BASE_URL", llm_cfg.get("base_url", "http://localhost:11434"))

    if not check_ollama(base_url, model):
        logger.warning(
            "[LLM] Ollama not reachable at %s or model '%s' not found — "
            "falling back to MockLLM. (ollama serve && ollama pull %s)",
            base_url, model, model,
        )
        return MockLLM()

    logger.info("[LLM] Using Ollama: model=%s base_url=%s", model, base_url)
    return OllamaClient(model=model, base_url=base_url)


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


def contract_audit_meta(contract: Dict[str, Any]) -> Dict[str, str]:
    """Extract audit-relevant contract identity for decision logs."""
    return {
        "agent_id": str(contract.get("agent_id", "unknown_agent")),
        "version": str(contract.get("version", "unknown_version")),
        "owner": str(contract.get("owner", "unknown_owner")),
        "effective_from": str(contract.get("effective_from", "unknown_effective_from")),
    }


def log_audit_event(level: int, event: str, fields: Dict[str, Any]) -> None:
    """Log audit events in a stable, multi-line format for terminal readability."""
    lines = [f"[AUDIT][{event}]"]
    for key, value in fields.items():
        prefix = f"  - {key}: "
        wrapped = textwrap.fill(
            str(value),
            width=100,
            initial_indent=prefix,
            subsequent_indent=" " * len(prefix),
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines.append(wrapped)
    logger.log(level, "\n".join(lines))


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
    contract_meta = contract_audit_meta(contract)
    llm = _build_llm(config)

    log_audit_event(
        logging.INFO,
        "CONTRACT_LOAD",
        {
            "contract_agent_id": contract_meta["agent_id"],
            "contract_version": contract_meta["version"],
            "contract_owner": contract_meta["owner"],
            "contract_effective_from": contract_meta["effective_from"],
        },
    )

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

    # 3. Agent: reason over context via LLM
    proposal = agent_reason(context, config, llm)
    log_audit_event(
        logging.INFO,
        "PROPOSAL_EMIT",
        {
            "dfid": proposal.dfid,
            "agent_id": proposal.agent_id,
            "policy_kind": proposal.policy_kind,
            "params": json.dumps(proposal.params, ensure_ascii=True, sort_keys=True),
            "confidence": proposal.confidence,
            "justification": proposal.justification or "",
        },
    )
    agent_mode = "Ollama" if isinstance(llm, OllamaClient) else "MockLLM"
    print(f"\n[3] Agent [{agent_mode}]: Reasoning over context...")
    print(f"    Proposal: {proposal.policy_kind} {proposal.params.get('quantity')} "
          f"{proposal.params.get('instrument')}")
    print(f"    Justification: {(proposal.justification or '')[:90]}")

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
        log_audit_event(
            logging.WARNING,
            "PROPOSAL_REJECT",
            {
                "dfid": proposal.dfid,
                "policy_kind": proposal.policy_kind,
                "reason": reason,
                "contract_agent_id": contract_meta["agent_id"],
                "contract_version": contract_meta["version"],
                "contract_owner": contract_meta["owner"],
                "contract_effective_from": contract_meta["effective_from"],
            },
        )
        print(f"    REJECT: {reason}")
        print(f"\n[5] DIR blocked catastrophic action. No API call. Escalation: Human notified.")
    else:
        log_audit_event(
            logging.INFO,
            "PROPOSAL_ACCEPT",
            {
                "dfid": proposal.dfid,
                "policy_kind": proposal.policy_kind,
                "reason": reason,
                "contract_agent_id": contract_meta["agent_id"],
                "contract_version": contract_meta["version"],
                "contract_owner": contract_meta["owner"],
                "contract_effective_from": contract_meta["effective_from"],
            },
        )
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
    proposal2 = agent_reason(context2, config, llm)
    log_audit_event(
        logging.INFO,
        "PROPOSAL_EMIT",
        {
            "dfid": proposal2.dfid,
            "agent_id": proposal2.agent_id,
            "policy_kind": proposal2.policy_kind,
            "params": json.dumps(proposal2.params, ensure_ascii=True, sort_keys=True),
            "confidence": proposal2.confidence,
            "justification": proposal2.justification or "",
        },
    )
    print(f"    Proposal: {proposal2.policy_kind} {proposal2.params.get('quantity')} ETH")
    verdict2, reason2 = validate_proposal(proposal2, base_ctx, allowed_agents=[agent_id])
    ok2, _ = validate_order_against_contract(proposal2, contract, config)
    if ok2 and verdict2 == "ACCEPT":
        log_audit_event(
            logging.INFO,
            "PROPOSAL_ACCEPT",
            {
                "dfid": proposal2.dfid,
                "policy_kind": proposal2.policy_kind,
                "reason": reason2,
                "contract_agent_id": contract_meta["agent_id"],
                "contract_version": contract_meta["version"],
                "contract_owner": contract_meta["owner"],
                "contract_effective_from": contract_meta["effective_from"],
            },
        )
        execute_and_audit(proposal2, store, dfid2)
        print(f"    Verdict: ACCEPT - executed.")
    else:
        log_audit_event(
            logging.WARNING,
            "PROPOSAL_REJECT",
            {
                "dfid": proposal2.dfid,
                "policy_kind": proposal2.policy_kind,
                "reason": reason2,
                "contract_agent_id": contract_meta["agent_id"],
                "contract_version": contract_meta["version"],
                "contract_owner": contract_meta["owner"],
                "contract_effective_from": contract_meta["effective_from"],
            },
        )
        print(f"    Verdict: {verdict2} - {reason2}")
    print("=" * 80)


if __name__ == "__main__":
    main()

