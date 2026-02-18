#!/usr/bin/env python3
"""
31_finance_trading - Topology A (EOAM) with full ROA agents backed by LLM (Ollama).

- Missions and Responsibility Contracts from config.yaml (ROA Manifesto §3)
- Explain → Policy → Self-Check → Proposal lifecycle via LLM (§4)
- Event bus, scope-based subscription, priority arbitration, DIM, dynamic PositionAgents (§2 EOAM)

Run from repo root: python samples/31_finance_trading/run.py
Requires: pip install -e .  and  pip install pyyaml
Optional: run Ollama locally (ollama serve, ollama pull llama3.2) or use MockLLM (env USE_MOCK_LLM=1).
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from dir_runtime import PolicyProposal, ResponsibilityContract, create_event_bus
from dir_runtime.dim import validate_proposal
from dir_runtime.logging_utils import log_with_dfid
from dir_runtime.news_generator import NewsGenerator
from dir_runtime.quote_generator import QuoteGenerator

try:
    from .llm_client import MockLLM, OllamaClient
    from .orchestrator import EOAMOrchestrator
    from .roa_agents import ROAInstrumentAgent, ROANewsScorerAgent
except ImportError:
    from llm_client import MockLLM, OllamaClient
    from orchestrator import EOAMOrchestrator
    from roa_agents import ROAInstrumentAgent, ROANewsScorerAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load YAML config. Requires PyYAML."""
    try:
        import yaml
    except ImportError:
        raise ImportError("This sample requires PyYAML. Install with: pip install pyyaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_llm(config: Dict[str, Any], use_mock: bool = False) -> Any:
    """Build LLM client from config (Ollama or MockLLM)."""
    if use_mock:
        return MockLLM(policy_action="HOLD", policy_confidence=0.8)
    defaults = config.get("llm_defaults", {})
    model = defaults.get("model", "llama3.2")
    base_url = defaults.get("base_url", "http://localhost:11434")
    return OllamaClient(model=model, base_url=base_url)


def build_agents(config: Dict[str, Any], llm: Any) -> tuple[List[Any], List[Any], Dict[str, Any] | None]:
    """
    Build instrument agents, news agent, and position template from config.
    Returns (instrument_agents, news_agents, position_template).
    """
    instruments: List[Any] = []
    news_agents: List[Any] = []
    position_template: Dict[str, Any] | None = None
    sim = config.get("simulation", {})
    threshold = sim.get("news_score_threshold", 0.6)

    for agent_cfg in config.get("agents", []):
        agent_type = agent_cfg.get("type")
        agent_id = agent_cfg.get("agent_id", "")
        contract_dict = dict(agent_cfg.get("contract", {}))
        contract_dict["agent_id"] = agent_id
        contract = ResponsibilityContract(**contract_dict)

        if agent_type == "instrument":
            scope = agent_cfg.get("scope")
            if scope:
                instruments.append(ROAInstrumentAgent(contract, llm, instrument=scope))
        elif agent_type == "news_scorer":
            news_agents.append(
                ROANewsScorerAgent(contract, llm, score_threshold=threshold)
            )
        elif agent_type == "position":
            position_template = agent_cfg

    return instruments, news_agents, position_template


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_config(config_path)

    use_mock_llm = os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    llm = build_llm(config, use_mock=use_mock_llm)
    if use_mock_llm:
        logger.info("Using MockLLM (no Ollama required)")

    sim = config.get("simulation", {})
    instruments = sim.get("instruments", ["BTC-USD", "ETH-USD"])
    initial_prices = sim.get("initial_prices", {})
    simulation_ticks = sim.get("simulation_ticks", 20)
    tick_interval_sec = sim.get("tick_interval_sec", 0.3)
    news_every_n_ticks = sim.get("news_every_n_ticks", 5)
    max_news_events = sim.get("max_news_events", 4)
    seeds = sim.get("seeds", {})
    quote_seed = seeds.get("quote", 42)
    news_seed = seeds.get("news", 43)

    instrument_agents, news_agents, position_template = build_agents(config, llm)
    if not instrument_agents:
        raise ValueError("Config must define at least one instrument agent")

    bus = create_event_bus(backend="memory")
    priority_matrix = config.get("priority_matrix", {})
    orch = EOAMOrchestrator(bus=bus, priority_matrix=priority_matrix)
    if position_template:
        orch.set_spawn_deps(llm, position_template)

    for agent in instrument_agents:
        orch.register_agent(agent)
    for agent in news_agents:
        orch.register_news_agent(agent)

    generators: List[QuoteGenerator] = []
    for i, inst in enumerate(instruments):
        gen = QuoteGenerator(
            instrument=inst,
            initial_price=initial_prices.get(inst, 1000.0),
            volatility=0.02,
            seed=quote_seed + i,
            tick_interval_sec=0,
        )
        generators.append(gen)

    news_gen = NewsGenerator(
        instruments=instruments,
        seed=news_seed,
        interval_sec=1.0,
        random_interval=False,
    )

    def validate_proposal_shim(proposal: PolicyProposal) -> tuple[str, str]:
        return validate_proposal(proposal, context={}, allowed_agents=None)

    print("=" * 70)
    print("EOAM Live Simulation - ROA agents (LLM), config-driven missions")
    print("=" * 70)

    tick_count = 0
    news_count = 0

    for _ in range(simulation_ticks):
        inst_index = tick_count % len(instruments)
        quote_gen = generators[inst_index]
        tick_payload = quote_gen.next_tick().to_payload()
        scope = tick_payload["instrument"]
        dfid = orch.emit_observation(tick_payload, scope=scope)

        winner = orch.arbitrate(dfid)
        orch.clear_pending(dfid)

        if winner:
            result, reason = validate_proposal_shim(winner)
            log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", result, reason)
            if result == "ACCEPT":
                if winner.policy_kind == "OPEN_POSITION":
                    entry_price = winner.params.get("price", tick_payload.get("price"))
                    orch.spawn_position_agent(
                        winner.params.get("instrument", scope),
                        entry_price,
                    )
                else:
                    log_with_dfid(
                        logger, dfid, logging.INFO,
                        "Mock execution: %s", winner.policy_kind,
                    )

        tick_count += 1

        if tick_count % news_every_n_ticks == 0 and news_count < max_news_events:
            news_payload = next(news_gen.news_payloads(max_events=1, sleep_between=False))
            news_dfid = orch.emit_news(news_payload)
            news_winner = orch.arbitrate(news_dfid)
            orch.clear_pending(news_dfid)
            if news_winner:
                result, _ = validate_proposal_shim(news_winner)
                log_with_dfid(
                    logger, news_dfid, logging.INFO,
                    "News cycle winner: %s DIM=%s",
                    news_winner.policy_kind, result,
                )
            news_count += 1

        if tick_interval_sec > 0:
            time.sleep(tick_interval_sec)

    print("\n" + "=" * 70)
    print("[SUMMARY] EOAM Live Simulation")
    print("=" * 70)
    print(f"  Ticks: {tick_count}, News events: {news_count}")
    print(f"  Position agents spawned: {len(orch._position_agents)}")
    print(f"  Bus events: {bus.event_count}")


if __name__ == "__main__":
    main()
