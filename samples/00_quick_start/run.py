#!/usr/bin/env python3
"""
00_quick_start — Minimal example preventing "Comma Catastrophe".

Demonstrates how DIR (DecisionRuntime) protects against language model
misinterpretation of numbers (e.g., "15,500" interpreted as 15500.0).

Run: python samples/00_quick_start/run.py
"""
from __future__ import annotations

import sys
import json
import re
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT / "samples") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "samples"))

from dir_core import DecisionRuntime, PolicyProposal, new_dfid
from dir_core.storage import memory_storage
from shared.config import load_yaml_config
from shared.llm.clients import OllamaClient, GeminiClient, MockLLMClient, check_ollama

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Mute internal DIR and adapter logs for maximum clarity in this showcase
logging.getLogger("dir_core").setLevel(logging.WARNING)
logging.getLogger("shared").setLevel(logging.WARNING)

def max_order_size_validator(
    proposal: PolicyProposal, 
    ctx: Dict[str, Any], 
    contract: Dict[str, Any]
) -> str | None:
    """DIM Validator: Verifies if order value does not exceed the allowed limit."""
    if proposal.policy_kind not in ("BUY", "SELL"):
        return None
    
    qty_raw = proposal.params.get("quantity", 0.0)
    try:
        qty = float(str(qty_raw).replace(",", ""))
    except (ValueError, TypeError):
        qty = 0.0
        
    price_usd = ctx.get("web", {}).get("current_price_eth_usd", 2500.0)
    value_usd = qty * price_usd
    
    max_usd = contract.get("permissions", {}).get("max_order_size_usd", float("inf"))
    
    if value_usd > max_usd:
        return (
            f"ORDER_VALUE_EXCEEDED: Value {value_usd:,.2f} USD "
            f"exceeds allowed contract limit of {max_usd:,.2f} USD."
        )
    return None

def parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON from model response (handles markdown)."""
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
        return None


def normalize_confidence(raw: Any) -> float:
    """Coerce LLM confidence into PolicyProposal range [0.0, 1.0] (untrusted input)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    # Whole numbers in (1, 100] are often "percent" style (e.g. 95 -> 0.95, 2 -> 0.02).
    if 1.0 < v <= 100.0 and v == int(v):
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _build_llm(config: Dict[str, Any]) -> Any:
    """Build LLM client from config. Falls back to MockLLM if Ollama is unreachable."""
    llm_cfg = config.get("llm_defaults", {})
    provider = str(llm_cfg.get("provider", "ollama")).lower()
    
    # We define a mock strategy to simulate the "Comma Catastrophe"
    def mock_strategy(prompt: str, system: Optional[str]) -> str:
        return json.dumps({
            "policy_kind": "BUY",
            "params": {"instrument": "ETH-USD", "quantity": 15500.0},
            "confidence": 0.95,
            "justification": "Market signal says buy 15,500 ETH. Interpreting as 15500 pieces and ignoring potential risks."
        })

    if os.getenv("USE_MOCK_LLM", "").strip() in ("1", "true", "yes") or provider == "mock":
        logger.info("Using MockLLM as explicitly configured.")
        return MockLLMClient(strategy=mock_strategy)

    if provider == "gemini":
        model = os.getenv("GEMINI_MODEL", llm_cfg.get("model", "gemini-1.5-pro"))
        api_key = os.getenv("GEMINI_API_KEY", llm_cfg.get("api_key", ""))
        logger.info("Using Gemini: model=%s", model)
        return GeminiClient(model=model, api_key=api_key)

    # Default to Ollama
    model = os.getenv("OLLAMA_MODEL", llm_cfg.get("model", "gemma3:4b"))
    base_url = os.getenv("OLLAMA_BASE_URL", llm_cfg.get("base_url", "http://localhost:11434"))

    if not check_ollama(base_url, model):
        logger.warning(
            "Ollama not reachable at %s (model: %s). Falling back to MockLLM.",
            base_url,
            model,
        )
        return MockLLMClient(strategy=mock_strategy)

    logger.info("Using Ollama: model=%s base_url=%s", model, base_url)
    return OllamaClient(model=model, base_url=base_url)

def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config = load_yaml_config(sample_dir / "config.yaml")
    contract = config.get("contract", {})
    agent_id = contract.get("agent_id", "trading_bot_01")

    logger.info("=" * 80)
    logger.info(" DIR Quick Start: Comma Catastrophe ")
    logger.info("=" * 80)

    # 1. Initialize DIR environment (in-memory storage for clean code)
    runtime = DecisionRuntime(memory_storage())
    
    # 2. Handshake: Register agent contract
    hr = runtime.register_agent(agent_id, contract, agent_version=contract.get("version", "1.0.0"))
    if not hr.accepted:
        logger.error("Agent registration rejected: %s", hr.reason)
        return
        
    logger.info("[1] Agent registered.")
    logger.info(f"    Contract: order limit = {contract.get('permissions', {}).get('max_order_size_usd', 0):,.0f} USD")
    logger.info("-" * 80)

    # 3. LLM Setup
    llm = _build_llm(config)
    
    # 4. Input Scenario
    mock_web = config.get("mock_web", {})
    signal = {
        "action": "BUY", 
        "amount_str": mock_web.get("inject", {}).get("suggested_position_eth", "15,500") + " ETH",
        "note": mock_web.get("inject", {}).get("note", "")
    }
    logger.info("[2] Test scenario - external signal: %s", signal)
    logger.info(f"    LLM is processing the signal...")
    
    current_price_eth_usd = mock_web.get("prices", {}).get("ETH-USD", 2500.0)
    
    prompt = (
        f"Analyze signal: {signal}.\n"
        f"Current price ETH-USD: {current_price_eth_usd}.\n"
        "Output ONLY JSON with keys: policy_kind (BUY/SELL/HOLD), "
        "params (dict with instrument, quantity as a number), "
        "confidence (float strictly between 0.0 and 1.0), justification."
    )
    raw_response = llm.generate(prompt, system=contract.get("mission"))
    logger.info(f"    Raw LLM response: {raw_response}")
    
    parsed = parse_llm_json(raw_response)
    if not parsed:
        logger.error("Failed to parse LLM response. Exiting.")
        return
    
    # 5. Formulation of proposal (User Space)
    conf_raw = parsed.get("confidence", 0.0)
    conf = normalize_confidence(conf_raw)
    if conf != conf_raw:
        logger.info(f"    Normalized confidence from LLM value {conf_raw!r} -> {conf}")

    proposal = PolicyProposal(
        dfid=new_dfid(),
        agent_id=agent_id,
        policy_kind=parsed.get("policy_kind", "HOLD"),
        params=parsed.get("params", {}),
        confidence=conf,
        justification=parsed.get("justification", "")
    )
    
    logger.info("")
    logger.info("[3] Agent Reasoning (LLM Proposal):")
    logger.info(f"    Action: {proposal.policy_kind} {proposal.params.get('quantity')} {proposal.params.get('instrument')}")
    logger.info(f"    Justification: '{proposal.justification}'")
    logger.info("-" * 80)
    
    # 6. DIM: Safety verification (Kernel Space)
    logger.info("[4] DIR Runtime (DIM) - verifying proposal...")
    
    current_price_eth_usd = mock_web.get("prices", {}).get("ETH-USD", 2500.0)
    verdict, reason = runtime.evaluate_proposal(
        proposal,
        raw_web_context={"current_price_eth_usd": current_price_eth_usd},
        allowed_agents=[agent_id],
        contract=contract,
        custom_validators=[max_order_size_validator],
        record_audit=False
    )
    
    if verdict == "ACCEPT":
        logger.info("ACCEPTED: %s. Order is sent to exchange.", reason)
    else:
        logger.info("REJECTED: %s", reason)
        logger.info("    -> DIR prevented the catastrophic order hallucinated by the LLM.")
        
    logger.info("=" * 80)

if __name__ == "__main__":
    main()
