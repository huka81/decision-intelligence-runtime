#!/usr/bin/env python3
"""
31_finance_trading — EOAM trading simulation with config-driven ROA agents and LLM.

Topology: A — EOAM. Mechanisms: EventBus, priority arbitration, DIM, AgentRegistry,
ContextStore, decision audit telemetry, dynamic position agents.

Run from repo root: python samples/31_finance_trading/run.py
LLM: Ollama, Gemini (API key env), or Mock (USE_MOCK_LLM=1).
"""
from __future__ import annotations

import logging
import os
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

import __init__  # noqa: F401 - loads .env via package __init__.py

from dir_core import (
    AgentRegistry,
    ContextStore,
    PolicyProposal,
    ResponsibilityContract,
    create_event_bus,
    validate_proposal,
)
from dir_core.utils.logging_utils import log_with_dfid
from shared.bootstrap import database_connection_summary, setup_environment
from shared.config import load_yaml_config

try:
    from .dir_kernel_wiring import (
        SimulationKernelContext,
        register_config_agents,
        register_spawned_position_agent,
    )
    from .mocks import NewsGenerator, QuoteGenerator, make_mock_strategy
    from .orchestrator import EOAMOrchestrator
    from .report_generator import generate_html_report
    from .roa_agents import ROAInstrumentAgent, ROANewsScorerAgent
    from .telemetry import (
        complete_simulation_audit,
        count_decision_audit_rows_for_simulation,
        record_agent_decision,
        record_market_tick,
        record_news_generated,
        record_position_closed,
        record_position_event,
        record_position_exposure_updated,
        record_position_spawned,
        start_simulation_audit,
    )
except ImportError:
    from dir_kernel_wiring import (
        SimulationKernelContext,
        register_config_agents,
        register_spawned_position_agent,
    )
    from mocks import NewsGenerator, QuoteGenerator, make_mock_strategy
    from orchestrator import EOAMOrchestrator
    from report_generator import generate_html_report
    from roa_agents import ROAInstrumentAgent, ROANewsScorerAgent
    from telemetry import (
        complete_simulation_audit,
        count_decision_audit_rows_for_simulation,
        record_agent_decision,
        record_market_tick,
        record_news_generated,
        record_position_closed,
        record_position_event,
        record_position_exposure_updated,
        record_position_spawned,
        start_simulation_audit,
    )

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_agents(
    config: Dict[str, Any],
    env: Any,
    *,
    kernel_ctx: SimulationKernelContext | None = None,
) -> tuple[List[Any], List[Any], Dict[str, Any] | None]:
    """
    Build instrument agents, news agent, and position template from config.
    Returns (instrument_agents, news_agents, position_template).
    """
    llm = env.llm
    contracts_provider = env.contracts
    
    instruments: List[Any] = []
    news_agents: List[Any] = []
    position_template: Dict[str, Any] | None = None
    sim = config.get("simulation", {})
    threshold = sim.get("news_score_threshold", 0.6)

    for agent_cfg in config.get("agents", []):
        agent_type = agent_cfg.get("type")
        agent_id = agent_cfg.get("agent_id", "")
        
        # Load contract using ContractProvider instead of raw config
        contract = contracts_provider.get_contract(agent_id)

        if agent_type == "instrument":
            scope = agent_cfg.get("scope")
            if scope:
                instruments.append(
                    ROAInstrumentAgent(
                        contract, llm, instrument=scope, kernel_ctx=kernel_ctx,
                    )
                )
        elif agent_type == "news_scorer":
            news_agents.append(
                ROANewsScorerAgent(
                    contract, llm, score_threshold=threshold, kernel_ctx=kernel_ctx,
                )
            )
        elif agent_type == "position":
            position_template = agent_cfg

    return instruments, news_agents, position_template


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_yaml_config(config_path)

    env = setup_environment(
        config,
        mock_llm_strategy=make_mock_strategy(),
        config_path=str(config_path),
    )
    llm = env.llm

    kernel_ctx = SimulationKernelContext()
    registry = AgentRegistry(storage=env.repository.agent_registry)
    ctx_store = ContextStore(storage=env.repository.context)
    kernel_ctx.context_store = ctx_store
    register_config_agents(registry, env.contracts, config.get("agents", []))

    sim = config.get("simulation", {})
    instruments = sim.get("instruments", ["BTC-USD", "ETH-USD"])
    initial_prices = sim.get("initial_prices", {})
    simulation_ticks = sim.get("simulation_ticks") or sim.get("simulation_ticks", 20)
    simulation_max_seconds = sim.get("simulation_max_seconds")
    tick_interval_sec = sim.get("tick_interval_sec", 0.3)
    news_every_n_ticks = sim.get("news_every_n_ticks", 5)
    max_news_events = sim.get("max_news_events", 4)
    seeds = sim.get("seeds", {})
    quote_seed = seeds.get("quote", 42)
    news_seed = seeds.get("news", 43)

    instrument_agents, news_agents, position_template = build_agents(
        config, env, kernel_ctx=kernel_ctx,
    )
    if not instrument_agents:
        raise ValueError("Config must define at least one instrument agent")

    bus = create_event_bus(backend="memory")
    priority_matrix = config.get("priority_matrix", {})
    orch = EOAMOrchestrator(bus=bus, priority_matrix=priority_matrix)
    if position_template:
        orch.set_spawn_deps(llm, position_template)
    orch.set_kernel_context(kernel_ctx)

    for agent in instrument_agents:
        orch.register_agent(agent)
    for agent in news_agents:
        orch.register_news_agent(agent)

    quote_generators: List[QuoteGenerator] = []
    for i, inst in enumerate(instruments):
        gen = QuoteGenerator(
            instrument=inst,
            initial_price=initial_prices.get(inst, 1000.0),
            volatility=0.02,
            seed=quote_seed + i,
            tick_interval_sec=0,
        )
        quote_generators.append(gen)

    news_gen = NewsGenerator(
        instruments=instruments,
        seed=news_seed,
        interval_sec=1.0,
        random_interval=False,
    )

    def validate_proposal_shim(proposal: PolicyProposal) -> tuple[str, str]:
        return validate_proposal(proposal, context={}, allowed_agents=None)

    # Persist simulation only via canonical StorageBundle.decision_audit.
    data_dir = sample_dir / "data"
    data_dir.mkdir(exist_ok=True)
    bundle = env.repository
    simulation_id = start_simulation_audit(bundle, config)
    kernel_ctx.simulation_id = simulation_id
    logger.info("Simulation ID: %s", simulation_id)
    logger.info("Persistence: %s", database_connection_summary(config))
    logger.info(
        "Decision audit backend: %s",
        type(bundle.decision_audit).__name__,
    )
    
    last_prices: Dict[str, float] = dict(initial_prices)

    print("=" * 70)
    print("EOAM Live Simulation - ROA agents (LLM), config-driven missions")
    print("=" * 70)

    tick_count = 0
    news_count = 0
    start_time = time.monotonic()
    
    try:
        while tick_count < simulation_ticks:
            if simulation_max_seconds is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= simulation_max_seconds:
                    logger.info("Simulation ended: max_seconds (%.1fs) reached", simulation_max_seconds)
                    break

            inst_index = tick_count % len(instruments)
            quote_gen = quote_generators[inst_index]
            tick_payload = quote_gen.next_tick().to_payload()
            scope = tick_payload["instrument"]
            last_prices[scope] = tick_payload.get("price", last_prices.get(scope, 1000.0))

            dfid = orch.emit_observation(tick_payload, scope=scope)
            record_market_tick(bundle, simulation_id, tick_count, tick_payload, dfid)

            winner = orch.arbitrate(dfid)
            orch.clear_pending(dfid)

            if winner:
                result, reason = validate_proposal_shim(winner)
                record_agent_decision(
                    bundle, simulation_id, tick_count, winner, result, reason,
                    event_type="observation",
                )
                log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", result, reason)
                if result == "ACCEPT":
                    # NOTE: OPEN_POSITION is deprecated - positions should only be opened via NEWS_QUALIFIED
                    # This code path remains for backwards compatibility but should not be triggered with current config
                    if winner.policy_kind == "OPEN_POSITION":
                        logger.warning("OPEN_POSITION detected - this is deprecated. Positions should be opened via NEWS_QUALIFIED only.")
                        entry_price_val = winner.params.get("price", tick_payload.get("price", 1000.0))
                        if not isinstance(entry_price_val, (int, float)):
                            entry_price_val = 1000.0
                        # Get max_exposure from position_template config
                        max_exposure = 10000.0
                        if position_template:
                            max_exposure = position_template.get("contract", {}).get("max_exposure", 10000.0)
                        quantity = max_exposure / entry_price_val if entry_price_val > 0 else 0.0
                        agent = orch.spawn_position_agent(
                            winner.params.get("instrument", scope),
                            float(entry_price_val),
                            initial_exposure=max_exposure,
                            quantity=quantity,
                        )
                        record_position_spawned(
                            bundle,
                            simulation_id,
                            agent.position_id,
                            winner.params.get("instrument", scope),
                            tick_count,
                            float(entry_price_val),
                            max_exposure,
                            quantity,
                        )
                        register_spawned_position_agent(registry, agent.contract)
                        bundle.lifecycle.record_transition(
                            simulation_id,
                            "POSITION_SPAWN",
                            agent.agent_id,
                        )
                    elif winner.policy_kind in ("CLOSE", "TAKE_PROFIT"):
                        # Position closure (CLOSE or TAKE_PROFIT): update database and cleanup agent
                        if hasattr(winner, "params") and winner.params.get("position_id"):
                            position_id = winner.params["position_id"]
                            close_reason = winner.params.get("close_reason", winner.policy_kind)
                            close_price = winner.params.get("price", 0.0)
                            pnl_pct = winner.params.get("pnl_pct", 0.0)
                            pnl_usd = winner.params.get("unrealized_pnl_usd", 0.0)
                            
                            record_position_event(
                                bundle,
                                simulation_id,
                                position_id,
                                tick_count,
                                winner.policy_kind,
                                close_price,
                                winner.justification,
                            )

                            record_position_closed(
                                bundle,
                                simulation_id,
                                position_id,
                                tick_count,
                                close_price,
                                close_reason,
                            )

                            registry.set_agent_status(
                                winner.agent_id,
                                "RETIRED",
                                "POSITION_CLOSED",
                            )
                            bundle.lifecycle.record_transition(
                                simulation_id,
                                winner.agent_id,
                                "RETIRED",
                            )

                            orch.cleanup_position_agent(winner.agent_id)
                            
                            log_with_dfid(
                                logger, dfid, logging.INFO,
                                "=== POSITION %s CLOSED ===",
                                position_id,
                            )
                            log_with_dfid(
                                logger, dfid, logging.INFO,
                                "    Reason: %s | Exit Price: $%.2f | P&L: %.2f%% ($%.2f)",
                                close_reason, close_price, pnl_pct * 100, pnl_usd,
                            )
                    elif winner.policy_kind == "REDUCE":
                        # Position reduction: update exposure in database
                        if hasattr(winner, "params") and winner.params.get("position_id"):
                            position_id = winner.params["position_id"]
                            new_exposure = winner.params.get("new_exposure", 0.0)
                            
                            record_position_event(
                                bundle,
                                simulation_id,
                                position_id,
                                tick_count,
                                winner.policy_kind,
                                winner.params.get("price", 0.0),
                                winner.justification,
                            )

                            record_position_exposure_updated(
                                bundle,
                                simulation_id,
                                position_id,
                                new_exposure,
                            )
                            
                            log_with_dfid(
                                logger, dfid, logging.INFO,
                                "Position %s REDUCE: new exposure=$%.2f",
                                position_id, new_exposure,
                            )
                    else:
                        if hasattr(winner, "params") and winner.params.get("position_id"):
                            record_position_event(
                                bundle,
                                simulation_id,
                                winner.params["position_id"],
                                tick_count,
                                winner.policy_kind,
                                winner.params.get("price", 0.0),
                                winner.justification,
                            )
                        log_with_dfid(
                            logger, dfid, logging.INFO,
                            "Mock execution: %s", winner.policy_kind,
                        )

            tick_count += 1

            # News processing (every N ticks)
            if tick_count % news_every_n_ticks == 0 and news_count < max_news_events:
                news_payload = next(news_gen.news_payloads(max_events=1, sleep_between=False))
                news_dfid = orch.emit_news(news_payload)
                record_news_generated(bundle, simulation_id, news_payload, news_dfid)

                news_winner = orch.arbitrate(news_dfid)
                orch.clear_pending(news_dfid)
                if news_winner:
                    result, _ = validate_proposal_shim(news_winner)
                    record_agent_decision(
                        bundle,
                        simulation_id,
                        tick_count,
                        news_winner,
                        result,
                        "",
                        event_type="news",
                    )
                    log_with_dfid(
                        logger, news_dfid, logging.INFO,
                        "News cycle winner: %s DIM=%s",
                        news_winner.policy_kind, result,
                    )
                    if result == "ACCEPT" and news_winner.policy_kind == "NEWS_QUALIFIED":
                        affected = news_winner.params.get("instruments_affected", [])
                        headline = news_winner.params.get("headline", "")
                        # Get max_exposure from position_template config
                        max_exposure = 10000.0
                        if position_template:
                            max_exposure = position_template.get("contract", {}).get("max_exposure", 10000.0)
                        for inst in affected[:1]:  # Spawn one position per news
                            entry_price_raw = last_prices.get(inst) or initial_prices.get(inst) or 1000.0
                            entry_price = float(entry_price_raw)
                            # Calculate quantity based on exposure
                            quantity = max_exposure / entry_price if entry_price > 0 else 0.0
                            agent = orch.spawn_position_agent(
                                inst,
                                entry_price,
                                initial_exposure=max_exposure,
                                quantity=quantity,
                                parent_dfid=news_dfid,
                                parent_agent_id="news_scorer",
                                news_headline=headline,
                            )
                            record_position_spawned(
                                bundle,
                                simulation_id,
                                agent.position_id,
                                inst,
                                tick_count,
                                entry_price,
                                max_exposure,
                                quantity,
                                parent_dfid=news_dfid,
                                news_headline=headline,
                            )
                            register_spawned_position_agent(registry, agent.contract)
                            bundle.lifecycle.record_transition(
                                news_dfid,
                                "POSITION_SPAWN",
                                agent.agent_id,
                            )
                            # Clear logging for position opening
                            log_with_dfid(
                                logger, news_dfid, logging.INFO,
                                "═══════════════════════════════════════════════════════════════",
                            )
                            log_with_dfid(
                                logger, news_dfid, logging.INFO,
                                ">>> POSITION OPENED: %s",
                                agent.position_id,
                            )
                            log_with_dfid(
                                logger, news_dfid, logging.INFO,
                                "    Instrument: %s | Tick: %d | Entry Price: $%.2f",
                                inst, tick_count, entry_price,
                            )
                            log_with_dfid(
                                logger, news_dfid, logging.INFO,
                                "    Exposure: $%.2f | Quantity: %.6f",
                                max_exposure, quantity,
                            )
                            log_with_dfid(
                                logger, news_dfid, logging.INFO,
                                "    News: %s",
                                headline[:80] + "..." if len(headline) > 80 else headline,
                            )
                            log_with_dfid(
                                logger, news_dfid, logging.INFO,
                                "═══════════════════════════════════════════════════════════════",
                            )
                news_count += 1

            if tick_interval_sec > 0:
                time.sleep(tick_interval_sec)

            logger.info("Progress: tick %d/%d", tick_count, simulation_ticks)

        # Simulation completed successfully
        elapsed_seconds = time.monotonic() - start_time
        complete_simulation_audit(bundle, simulation_id, status="completed")
        audit_rows = count_decision_audit_rows_for_simulation(bundle, simulation_id)
        logger.info(
            "Decision audit rows for this simulation_id: %s "
            "(filter detail_json / details by simulation_id, not dfid prefix)",
            audit_rows,
        )
        if type(bundle.decision_audit).__name__ == "PgDecisionAuditStorage":
            esc = simulation_id.replace("'", "''")
            logger.info(
                "PostgreSQL sample: SELECT id, dfid, event FROM decision_audit_events "
                "WHERE detail_json->>'simulation_id' = '%s' ORDER BY id LIMIT 20;",
                esc,
            )

    except Exception as e:
        logger.error("Simulation failed: %s", e, exc_info=True)
        elapsed_seconds = time.monotonic() - start_time
        complete_simulation_audit(
            bundle, simulation_id, status="error", error_message=str(e),
        )
        raise

    print("\n" + "=" * 70)
    print("[SUMMARY] EOAM Live Simulation")
    print("=" * 70)
    print(f"  Ticks: {tick_count}, News events: {news_count}")
    print(f"  Position agents spawned: {len(orch._position_agents)}")
    print(f"  Bus events: {bus.event_count}")
    print(f"  Signal suppression: {orch._suppressed_signals} signals suppressed by Wake-up Predicates")

    # Generate report in ./results subfolder
    results_dir = sample_dir / "results"
    results_dir.mkdir(exist_ok=True)
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    report_path = results_dir / f"report_{report_date}_{tick_count}ticks.html"
    generate_html_report(
        simulation_id=simulation_id,
        bundle=env.repository,
        output_path=report_path,
        simulation_ticks=tick_count,
        news_count=news_count,
        elapsed_seconds=elapsed_seconds,
    )
    print(f"  Report: {report_path}")
    print(f"  Simulation ID: {simulation_id}")
    print()

    # Open HTML report in browser
    print(f"\nOpening report in browser: {report_path}")
    try:
        webbrowser.open(str(report_path.resolve()))
    except Exception as e:
        logger.error("Failed to open report in browser: %s", e)


if __name__ == "__main__":
    main()

