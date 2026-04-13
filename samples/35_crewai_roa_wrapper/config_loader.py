"""
35_crewai_roa_wrapper - Configuration loader for config.yaml.

Loads and validates the YAML config, building typed objects used by run.py:
  - LlmConfig       : LLM provider settings (model, base_url, temperature)
  - ClaimsContract  : Agent responsibility contract (from contracts.py)
  - context_store   : Authoritative order data dict for DIM validation
  - scenarios       : List of test scenario dicts

Usage:
    cfg = load_config()                         # loads config.yaml next to this file
    cfg = load_config("path/to/config.yaml")    # explicit path

Same pattern as 31_finance_trading config loading.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts import ClaimsContract
from dir_core.utils.config_loader import load_yaml_config

_DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"


# ---------------------------------------------------------------------------
# Typed config objects
# ---------------------------------------------------------------------------


@dataclass
class LlmConfig:
    """LLM provider settings loaded from llm_defaults section."""

    model: str
    base_url: str
    temperature: float = 0.2

    @classmethod
    def from_dict(cls, cfg: Dict[str, Any]) -> "LlmConfig":
        return cls(
            model=cfg["model"],
            base_url=cfg["base_url"],
            temperature=float(cfg.get("temperature", 0.2)),
        )

    def effective_model(self) -> str:
        """Return OLLAMA_MODEL env override or config value."""
        return os.getenv("OLLAMA_MODEL", self.model)

    def effective_base_url(self) -> str:
        """Return OLLAMA_BASE_URL env override or config value."""
        return os.getenv("OLLAMA_BASE_URL", self.base_url)


@dataclass
class ScenarioConfig:
    """Single test scenario from the scenarios section."""

    label: str
    claim: Optional[Dict[str, Any]] = None  # structured claim (dict)
    claim_text: Optional[str] = None  # natural language — LLM extracts claim
    expected: str = "ACCEPT"  # ACCEPT | REJECT | ESCALATE

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioConfig":
        claim = None
        claim_text = None
        if "claim_text" in d:
            claim_text = str(d["claim_text"]).strip()
        if "claim" in d:
            claim = {str(k): v for k, v in d["claim"].items()}
        if claim is None and claim_text is None:
            raise ValueError("Scenario must have 'claim' or 'claim_text'")
        return cls(
            label=d["label"],
            claim=claim,
            claim_text=claim_text,
            expected=str(d["expected"]).upper(),
        )


@dataclass
class CrewConfig:
    """CrewAI agent roles and goals from agent.crew section."""

    analyst_role: str
    analyst_goal: str
    decision_maker_role: str
    decision_maker_goal: str

    @classmethod
    def from_dict(cls, crew_cfg: Dict[str, Any]) -> "CrewConfig":
        return cls(
            analyst_role=str(crew_cfg.get("analyst_role", "Claims Analyst")),
            analyst_goal=str(crew_cfg.get("analyst_goal", "Analyze a customer refund claim and summarize eligibility.")),
            decision_maker_role=str(crew_cfg.get("decision_maker_role", "Decision Maker")),
            decision_maker_goal=str(crew_cfg.get("decision_maker_goal", "Based on analyst findings, produce a refund proposal as JSON. Use action=REFUND always. The DIR Kernel enforces all limits.")),
        )


@dataclass
class AppConfig:
    """Full parsed configuration for the Claims Agent demo."""

    llm: LlmConfig
    contract: ClaimsContract
    crew: CrewConfig
    context_store: Dict[str, Any]
    scenarios: List[ScenarioConfig]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_config(path: Optional[Path] = None) -> AppConfig:
    """
    Load and validate config.yaml. Returns AppConfig.

    Args:
        path: Path to config file. Defaults to config.yaml next to this module.

    Raises:
        FileNotFoundError: If config file is missing.
        KeyError: If required sections are absent.
        ValueError: If required fields have invalid values.
    """
    config_path = Path(path) if path else _DEFAULT_CONFIG
    raw = load_yaml_config(config_path)

    # LLM defaults
    llm_cfg = raw.get("llm_defaults")
    if not llm_cfg:
        raise KeyError("config.yaml missing required section: llm_defaults")
    llm = LlmConfig.from_dict(llm_cfg)

    # Agent contract and crew
    agent_cfg = raw.get("agent")
    if not agent_cfg:
        raise KeyError("config.yaml missing required section: agent")
    contract = ClaimsContract.from_config(agent_cfg)
    crew = CrewConfig.from_dict(agent_cfg.get("crew", {}))

    # Context Store - normalise keys to strings
    context_store_raw = raw.get("context_store", {})
    orders_raw = context_store_raw.get("orders", {})
    context_store: Dict[str, Any] = {
        "orders": {
            str(order_id): {str(k): v for k, v in order_data.items()}
            for order_id, order_data in orders_raw.items()
        }
    }

    # Scenarios
    scenarios_raw = raw.get("scenarios", [])
    scenarios = [ScenarioConfig.from_dict(s) for s in scenarios_raw]

    return AppConfig(
        llm=llm,
        contract=contract,
        crew=crew,
        context_store=context_store,
        scenarios=scenarios,
    )
