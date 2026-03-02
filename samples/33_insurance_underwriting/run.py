#!/usr/bin/env python3
"""
33_insurance_underwriting - Digital Underwriter (Decision Ledger & Proof-Carrying Intents).

Full ROA agent with LLM (Explain → Policy → Self-Check). Config-driven via config.yaml.
Topology C: system commits to Ledger only when agent provides valid Evidence Hash.

Run: python samples/33_insurance_underwriting/run.py
Optional: USE_MOCK_LLM=1 (no Ollama), LOG_LEVEL=DEBUG
"""

from __future__ import annotations

import logging
import os
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

from models import ClientApplication, UnderwritingContract
from report_generator import generate_html_report
from kernel import (
    AgentRegistry,
    ContextStore,
    DecisionIntegrityModule,
    DecisionLedger,
)
from roa_underwriter_agent import ROAUnderwriterAgent, DecisionCycleReport

try:
    from .llm_client import MockLLM, OllamaClient
except ImportError:
    from llm_client import MockLLM, OllamaClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load YAML config. Requires PyYAML."""
    try:
        import yaml
    except ImportError:
        raise ImportError("This sample requires PyYAML. Install: pip install pyyaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_llm(config: Dict[str, Any], use_mock: bool = False) -> Any:
    """Build LLM client from config (Ollama or MockLLM)."""
    if use_mock:
        return MockLLM()
    defaults = config.get("llm_defaults", {})
    model = defaults.get("model", "gemma3:12b")
    base_url = defaults.get("base_url", "http://localhost:11434")
    return OllamaClient(model=model, base_url=base_url)


def build_contract(config: Dict[str, Any]) -> UnderwritingContract:
    """Build UnderwritingContract from config."""
    uw = config.get("underwriting", {})
    agents = config.get("agents", [])
    agent_cfg = agents[0] if agents else {}
    contract_cfg = agent_cfg.get("contract", {})
    return UnderwritingContract(
        agent_id=agent_cfg.get("agent_id", "underwriter_agent"),
        version=agent_cfg.get("version", "1.0.0"),
        created_by=agent_cfg.get("created_by"),
        created_at=agent_cfg.get("created_at"),
        mission=agent_cfg.get("mission", "Underwrite insurance policies."),
        max_limit=contract_cfg.get("max_limit", uw.get("max_limit", 2_000_000)),
        prohibited_industries=contract_cfg.get(
            "prohibited_industries",
            uw.get("prohibited_industries", ["Fireworks", "CryptoMining"]),
        ),
    )


def build_scenarios(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build scenario list from config."""
    return config.get("scenarios", [])


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_config(config_path)

    use_mock_llm = os.environ.get("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    llm = build_llm(config, use_mock=use_mock_llm)
    if use_mock_llm:
        logger.info("Using MockLLM (no Ollama required)")

    contract = build_contract(config)
    logger.info(
        "Contract loaded: version=%s, created_by=%s, created_at=%s",
        contract.version, contract.created_by or "—", contract.created_at or "—",
    )
    registry = AgentRegistry(contract)
    context_store = ContextStore()
    ledger = DecisionLedger()
    dim = DecisionIntegrityModule(registry, context_store, ledger)

    agent = ROAUnderwriterAgent(registry, llm)

    scenarios = build_scenarios(config)
    if not scenarios:
        scenarios = [
            {"name": "Retail", "business_type": "Retail", "revenue": 500000, "industry": "Retail", "expect": "Policy Bound"},
            {"name": "Fireworks", "business_type": "Fireworks Factory", "revenue": 1000000, "industry": "Fireworks", "expect": "Prohibited Industry"},
            {"name": "Forged hash", "business_type": "Fireworks Factory", "revenue": 1000000, "industry": "Fireworks", "forge_evidence_hash": True, "expect": "Evidence Invalid"},
        ]

    print("=" * 70, flush=True)
    print("Digital Underwriter - Topology C (ROA + LLM, config-driven)", flush=True)
    print("=" * 70, flush=True)

    results: List[str] = []
    reports: List[DecisionCycleReport] = []
    for sc in scenarios:
        name = sc.get("name", "Scenario")
        print(f"\n[Scenario] {name}", flush=True)
        context = ClientApplication(
            business_type=sc.get("business_type", "Retail"),
            revenue=float(sc.get("revenue", 500000)),
            industry=sc.get("industry", "Retail"),
        )
        forge = sc.get("forge_evidence_hash", False)
        pci, report = agent.run_decision_cycle(context, forge_evidence_hash=forge)
        result = dim.verify_and_commit(pci, context)
        results.append(result)
        reports.append(report)
        expect = sc.get("expect")
        status = "OK" if (expect is None or result == expect) else f"EXPECTED {expect}"
        print(f"  Outcome: {result} ({status})", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("Summary", flush=True)
    print("=" * 70, flush=True)
    print(f"  Ledger entries (verified only): {len(ledger)}", flush=True)
    for i, (sc, res) in enumerate(zip(scenarios, results)):
        print(f"  {sc.get('name', i)}: {res}", flush=True)
    print("\n  Day Two prevention: Only verified decisions are bound.", flush=True)

    # Generate HTML report
    report_path = sample_dir / "report.html"
    generate_html_report(
        scenarios=scenarios,
        reports=reports,
        results=results,
        contract=contract.model_dump(),
        ledger_count=len(ledger),
        output_path=report_path,
    )
    print(f"\n  HTML report: {report_path.resolve()}", flush=True)
    webbrowser.open(report_path.resolve().as_uri())


if __name__ == "__main__":
    main()
