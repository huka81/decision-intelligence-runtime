#!/usr/bin/env python3
"""
08_custom_repo_psql — DIR Quick Start with a custom PostgreSQL repository.

Demonstrates the same scenario as 00_quick_start ("Comma Catastrophe") but
with DIR state persisted in PostgreSQL instead of the built-in SQLite
backend.  The storage layer is wired through dir_repo.py, which implements
all DIR storage protocols and returns a repository handle (`Repository` in
dir_repo — same shape as `dir_core.storage.StorageBundle`) backed by one
psycopg2 connection.  This sample only passes registry and context stores to
the managers used in the scenario.

Architecture difference vs 00_quick_start
-----------------------------------------
  00_quick_start:   store = ContextStore(db_path="data/quick_start.db")
                    registry = AgentRegistry(db_path="data/quick_start.db", ...)
  this sample:      conn = dir_repo.connect(cfg["database"])
                    repo = dir_repo.build_repository(conn)
                    registry = AgentRegistry(storage=repo.agent_registry, ...)
                    store = ContextStore(storage=repo.context)

Everything else — scenario logic, DIM validation, audit logging — is
identical.

Run from repo root:
  python samples/08_custom_repo_psql/run.py

Prerequisites:
  pip install -e .  and  pip install pyyaml psycopg2-binary

PostgreSQL setup (once):
  createuser dir_user
  createdb -O dir_user dir_quickstart
  psql -U dir_user -d dir_quickstart -c "ALTER USER dir_user PASSWORD 'dir_pass';"
  # Schema is applied automatically on first run (idempotent).

Override connection params via env:
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dir_core import (
    ContextStore,
    PolicyProposal,
    new_dfid,
    validate_proposal,
)
from dir_core.agent_registry import AgentRegistry
from dir_core.utils.config_loader import load_yaml_config
from dir_core.utils.llm_client import LLMClient, OllamaClient, check_ollama

try:
    from .dir_repo import apply_schema, build_repository, connect
    from .llm_client import MockLLM
except ImportError:
    from dir_repo import apply_schema, build_repository, connect
    from llm_client import MockLLM

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock Web Source (with prompt injection / ambiguous number)
# ---------------------------------------------------------------------------


def mock_fetch_market_data(
    config: Dict[str, Any], inject_prompt: bool = True
) -> Dict[str, Any]:
    """Simulate fetching data from external web source.

    Contains prompt injection and ambiguous locale number (15,500 vs 15.500).
    """
    mock = config.get("mock_web", {})
    prices = mock.get("prices", {"ETH-USD": 2500.0, "BTC-USD": 50000.0})
    scenario = (
        mock.get("inject", {}) if inject_prompt else mock.get("clean", {})
    )
    return {
        "source": "market_signal_feed",
        "suggested_position_eth": scenario.get("suggested_position_eth", "0"),
        "note": scenario.get("note", ""),
        "price_eth_usd": prices.get("ETH-USD", 2500.0),
        "price_btc_usd": prices.get("BTC-USD", 50000.0),
    }


# ---------------------------------------------------------------------------
# LLM Agent
# ---------------------------------------------------------------------------


def _build_system_prompt(mission: str) -> str:
    return (
        f"{mission} "
        "Analyze the market signal feed and propose a trading action. "
        "Respond with ONLY a valid JSON object — no markdown, no explanation. "
        'Keys: policy_kind ("BUY"|"SELL"|"HOLD"), '
        'params ({instrument: str, quantity: float, execution_type: str}), '
        "justification (string), confidence (float 0-1)."
    )


def _build_prompt(web_data: Dict[str, Any], config: Dict[str, Any]) -> str:
    prices = config.get("mock_web", {}).get("prices", {})
    eth_price = prices.get("ETH-USD", web_data.get("price_eth_usd", 0))
    btc_price = prices.get("BTC-USD", web_data.get("price_btc_usd", 0))
    return (
        f"Market Signal Feed:\n"
        f'- instrument: ETH-USD\n'
        f'- suggested_position_eth: '
        f'"{web_data.get("suggested_position_eth", "0")}"\n'
        f'- note: "{web_data.get("note", "")}"\n'
        f"\nCurrent prices:\n"
        f"- ETH-USD: ${eth_price:,.2f}\n"
        f"- BTC-USD: ${btc_price:,.2f}\n"
        f"\nRespond with ONLY valid JSON:\n"
        '{"policy_kind": "BUY", "params": {"instrument": "ETH-USD", '
        '"quantity": <float>, "execution_type": "MARKET"}, '
        '"justification": "<your reasoning>", "confidence": <float 0.0-1.0>}'
    )


def _parse_llm_response(raw: str) -> Optional[Dict[str, Any]]:
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
    """Agent reasoning stage (User Space).

    Builds a prompt from context, calls the LLM, parses the response into a
    PolicyProposal.  Falls back to HOLD with confidence=0 on parse failure.
    """
    web = context.get("web", {})
    mission = config.get("contract", {}).get(
        "mission", "You are a crypto trading agent."
    )
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
            params={
                "instrument": "ETH-USD",
                "quantity": 0.0,
                "execution_type": "MARKET",
            },
            justification="LLM response could not be parsed; defaulting to HOLD.",
            confidence=0.0,
        )

    return PolicyProposal(
        dfid=context["meta"]["dfid"],
        agent_id=context["meta"]["agent_id"],
        policy_kind=str(parsed.get("policy_kind", "HOLD")),
        params=parsed.get(
            "params",
            {"instrument": "ETH-USD", "quantity": 0.0, "execution_type": "MARKET"},
        ),
        justification=str(parsed.get("justification", "")),
        confidence=float(parsed.get("confidence", 0.0)),
    )


# ---------------------------------------------------------------------------
# LLM client factory
# ---------------------------------------------------------------------------


def _build_llm(config: Dict[str, Any]) -> LLMClient:
    llm_cfg = config.get("llm_defaults", {})

    if os.getenv("USE_MOCK_LLM", "").strip() in ("1", "true", "yes"):
        logger.info("[LLM] Using MockLLM (USE_MOCK_LLM=1)")
        return MockLLM()

    if not llm_cfg or str(llm_cfg.get("provider", "")).lower() == "mock":
        logger.info("[LLM] Using MockLLM (provider=mock or llm_defaults absent)")
        return MockLLM()

    model = os.getenv("OLLAMA_MODEL", llm_cfg.get("model", "gemma3:4b"))
    base_url = os.getenv(
        "OLLAMA_BASE_URL", llm_cfg.get("base_url", "http://localhost:11434")
    )

    if not check_ollama(base_url, model):
        logger.warning(
            "[LLM] Ollama not reachable at %s or model '%s' not found — "
            "falling back to MockLLM.",
            base_url, model,
        )
        return MockLLM()

    logger.info("[LLM] Using Ollama: model=%s base_url=%s", model, base_url)
    return OllamaClient(model=model, base_url=base_url)


# ---------------------------------------------------------------------------
# Contract validation
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
    prices = config.get("mock_web", {}).get(
        "prices", {"ETH-USD": 2500.0, "BTC-USD": 50000.0}
    )
    price = prices.get(instrument, prices.get("ETH-USD", 2500.0))
    value_usd = quantity * price
    perms = contract.get("permissions", contract)
    max_usd = perms.get("max_order_size_usd", float("inf"))
    if value_usd > max_usd:
        return False, (
            f"ORDER_VALUE_EXCEEDED: ~{value_usd:,.0f} USD exceeds "
            f"limit {max_usd:,.0f} USD "
            f"(quantity={quantity}, instrument={instrument})"
        )
    return True, "OK"


def contract_audit_meta(contract: Dict[str, Any]) -> Dict[str, str]:
    return {
        "agent_id": str(contract.get("agent_id", "unknown_agent")),
        "version":  str(contract.get("version", "unknown_version")),
        "owner":    str(contract.get("owner", "unknown_owner")),
        "effective_from": str(
            contract.get("effective_from", "unknown_effective_from")
        ),
    }


def log_audit_event(
    level: int, event: str, fields: Dict[str, Any]
) -> None:
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
    params = proposal.params
    logger.info(
        "[MOCK API] Would execute: %s %s %s @ %s",
        proposal.policy_kind,
        params.get("quantity"),
        params.get("instrument"),
        params.get("execution_type"),
    )
    return (
        "mock_receipt_"
        + hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()[:8]
    )


# ---------------------------------------------------------------------------
# Context Compiler
# ---------------------------------------------------------------------------


def compile_context(
    store: ContextStore,
    registry: AgentRegistry,
    agent_id: str,
    dfid: str,
    web_data: Dict[str, Any],
) -> Dict[str, Any]:
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
# Execution Orchestrator
# ---------------------------------------------------------------------------


def execute_and_audit(
    proposal: PolicyProposal,
    store: ContextStore,
    dfid: str,
) -> str:
    receipt = mock_exchange_api(proposal)
    store.update_session(
        dfid,
        {
            "audit": {
                "executed": True,
                "receipt": receipt,
                "policy_kind": proposal.policy_kind,
                "params": proposal.params,
            }
        },
    )
    return receipt


# ---------------------------------------------------------------------------
# Database connection helpers (env overrides for CI / Docker)
# ---------------------------------------------------------------------------


def _db_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge config["database"] with optional environment variable overrides."""
    cfg = dict(config.get("database", {}))
    overrides = {
        "host":     os.getenv("DB_HOST"),
        "port":     os.getenv("DB_PORT"),
        "dbname":   os.getenv("DB_NAME"),
        "user":     os.getenv("DB_USER"),
        "password": os.getenv("DB_PASS"),
    }
    for key, val in overrides.items():
        if val is not None:
            cfg[key] = int(val) if key == "port" else val
    return cfg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config = load_yaml_config(sample_dir / "config.yaml")

    contract = config.get("contract", {})
    agent_id = contract.get("agent_id", "crypto_position_manager_01")
    agent_version = contract.get("version", "1.2.0")
    contract_meta = contract_audit_meta(contract)
    llm = _build_llm(config)

    log_audit_event(
        logging.INFO,
        "CONTRACT_LOAD",
        {
            "contract_agent_id":       contract_meta["agent_id"],
            "contract_version":        contract_meta["version"],
            "contract_owner":          contract_meta["owner"],
            "contract_effective_from": contract_meta["effective_from"],
        },
    )

    # ------------------------------------------------------------------
    # Storage: connect to PostgreSQL, apply schema, open repository
    # ------------------------------------------------------------------
    db_cfg = _db_config(config)
    logger.info(
        "[DB] Connecting to PostgreSQL: host=%s port=%s dbname=%s user=%s",
        db_cfg.get("host"), db_cfg.get("port"),
        db_cfg.get("dbname"), db_cfg.get("user"),
    )
    conn = connect(db_cfg)
    apply_schema(conn)           # CREATE TABLE IF NOT EXISTS — idempotent
    repo = build_repository(conn)

    registry = AgentRegistry(
        storage=repo.agent_registry, supported_versions="1.x"
    )
    store = ContextStore(storage=repo.context)
    
    dfid = new_dfid()

    print("=" * 80)
    print("08_custom_repo_psql - DIR Quick Start (PostgreSQL backend)")
    print("=" * 80)

    # 1. Agent Registry: handshake
    hr = registry.handshake(agent_id, contract, agent_version=agent_version)
    if not hr.accepted:
        print(f"FATAL: Agent handshake failed: {hr.reason}")
        conn.close()
        return
    print(f"\n[1] Agent Registry: Handshake accepted (agent_id={agent_id})")
    print(f"    Stored in PostgreSQL table: agent_registry")

    # 2. Context Compiler
    web_data = mock_fetch_market_data(config, inject_prompt=True)
    print(f"\n[2] Context Compiler: Fetching from mock web source...")
    print(f"    Web data (raw): {json.dumps(web_data, indent=2)}")
    context = compile_context(store, registry, agent_id, dfid, web_data)
    print(f"    Session stored in PostgreSQL table: context_session (dfid={dfid[:8]}...)")

    # 3. Agent reasoning
    proposal = agent_reason(context, config, llm)
    log_audit_event(
        logging.INFO,
        "PROPOSAL_EMIT",
        {
            "dfid":       proposal.dfid,
            "agent_id":   proposal.agent_id,
            "policy_kind": proposal.policy_kind,
            "params":     json.dumps(
                proposal.params, ensure_ascii=True, sort_keys=True
            ),
            "confidence": proposal.confidence,
            "justification": proposal.justification or "",
        },
    )
    agent_mode = "Ollama" if isinstance(llm, OllamaClient) else "MockLLM"
    print(f"\n[3] Agent [{agent_mode}]: Reasoning over context...")
    print(
        f"    Proposal: {proposal.policy_kind} "
        f"{proposal.params.get('quantity')} "
        f"{proposal.params.get('instrument')}"
    )
    print(
        f"    Justification: {(proposal.justification or '')[:90]}"
    )

    # 4. DIM Validation
    perms = contract.get("permissions", {})
    print(f"\n[4] DIM Validation: Checking against contract...")
    print(
        f"    Contract: max_order_usd={perms.get('max_order_size_usd')}, "
        f"allowed_instruments={perms.get('allowed_instruments')}"
    )
    base_ctx = {"state": {}, "meta": context.get("meta", {})}
    verdict, reason = validate_proposal(
        proposal, base_ctx, allowed_agents=[agent_id]
    )
    if verdict == "ACCEPT":
        ok, contract_reason = validate_order_against_contract(
            proposal, contract, config
        )
        if not ok:
            verdict = "REJECT"
            reason = contract_reason

    if verdict == "REJECT":
        log_audit_event(
            logging.WARNING,
            "PROPOSAL_REJECT",
            {
                "dfid":        proposal.dfid,
                "policy_kind": proposal.policy_kind,
                "reason":      reason,
                **{f"contract_{k}": v for k, v in contract_meta.items()},
            },
        )
        print(f"    REJECT: {reason}")
        print(
            f"\n[5] DIR blocked catastrophic action. "
            f"No API call. Escalation: Human notified."
        )
    else:
        log_audit_event(
            logging.INFO,
            "PROPOSAL_ACCEPT",
            {
                "dfid":        proposal.dfid,
                "policy_kind": proposal.policy_kind,
                "reason":      reason,
                **{f"contract_{k}": v for k, v in contract_meta.items()},
            },
        )
        print(f"    ACCEPT: {reason}")
        receipt = execute_and_audit(proposal, store, dfid)
        print(f"\n[5] Execution Orchestrator: Mock API called. Receipt: {receipt}")

    print(
        f"\n[6] Summary: DFID={dfid[:8]}... verdict={verdict} "
        f"reason={reason[:50]}..."
    )
    print("=" * 80)

    # Bonus: second run with clean (non-injected) data — ACCEPT path
    print("\n--- BONUS: Run with correct data (no injection) ---")
    web_clean = mock_fetch_market_data(config, inject_prompt=False)
    dfid2 = new_dfid()
    context2 = compile_context(store, registry, agent_id, dfid2, web_clean)
    proposal2 = agent_reason(context2, config, llm)
    log_audit_event(
        logging.INFO,
        "PROPOSAL_EMIT",
        {
            "dfid":        proposal2.dfid,
            "agent_id":    proposal2.agent_id,
            "policy_kind": proposal2.policy_kind,
            "params":      json.dumps(
                proposal2.params, ensure_ascii=True, sort_keys=True
            ),
            "confidence":     proposal2.confidence,
            "justification":  proposal2.justification or "",
        },
    )
    print(
        f"    Proposal: {proposal2.policy_kind} "
        f"{proposal2.params.get('quantity')} ETH"
    )
    verdict2, reason2 = validate_proposal(
        proposal2, base_ctx, allowed_agents=[agent_id]
    )
    ok2, _ = validate_order_against_contract(proposal2, contract, config)
    if ok2 and verdict2 == "ACCEPT":
        log_audit_event(
            logging.INFO,
            "PROPOSAL_ACCEPT",
            {
                "dfid":        proposal2.dfid,
                "policy_kind": proposal2.policy_kind,
                "reason":      reason2,
                **{f"contract_{k}": v for k, v in contract_meta.items()},
            },
        )
        execute_and_audit(proposal2, store, dfid2)
        print(f"    Verdict: ACCEPT — executed.")
    else:
        log_audit_event(
            logging.WARNING,
            "PROPOSAL_REJECT",
            {
                "dfid":        proposal2.dfid,
                "policy_kind": proposal2.policy_kind,
                "reason":      reason2,
                **{f"contract_{k}": v for k, v in contract_meta.items()},
            },
        )
        print(f"    Verdict: {verdict2} — {reason2}")
    print("=" * 80)

    conn.close()
    logger.info("[DB] Connection closed.")


if __name__ == "__main__":
    main()
