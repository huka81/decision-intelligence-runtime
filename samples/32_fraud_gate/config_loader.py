"""
32_fraud_gate - Configuration loader for config.yaml.

Loads and validates the YAML config, building typed objects used by run.py:
  - llm           : LlmConfig (model, base_url) or None for MockLLM
  - agent         : AgentConfig (agent_id, mission, fallback_rules)
  - global_max_limit: JIT validator hard limit
  - scenarios     : List of test scenario dicts (context, snapshot, expected)

Usage:
    cfg = load_config()  # loads config.yaml next to this file
    cfg = load_config("path/to/config.yaml")  # explicit path

Same pattern as samples/31_finance_trading and samples/35_crewai_roa_wrapper.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.config_loader import load_yaml_config

_DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"


# ---------------------------------------------------------------------------
# Typed config objects
# ---------------------------------------------------------------------------


@dataclass
class LlmConfig:
    """LLM provider settings from llm_defaults section."""

    model: str
    base_url: str
    temperature: float = 0.2

    @classmethod
    def from_dict(cls, cfg: Dict[str, Any]) -> "LlmConfig":
        return cls(
            model=str(cfg.get("model", "gemma3:4b")),
            base_url=str(cfg.get("base_url", "http://localhost:11434")),
            temperature=float(cfg.get("temperature", 0.2)),
        )

    def effective_model(self) -> str:
        return os.getenv("OLLAMA_MODEL", self.model)

    def effective_base_url(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", self.base_url)


@dataclass
class FallbackRules:
    """Fallback decision rules when LLM fails or MockLLM is used."""

    block_amount_threshold: float
    block_high_risk_countries: List[str]
    allow_amount_max: float
    allow_velocity_max: int
    allow_device_prefix: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FallbackRules":
        countries = d.get("block_high_risk_countries", ["nigeria"])
        return cls(
            block_amount_threshold=float(d.get("block_amount_threshold", 5000)),
            block_high_risk_countries=[str(c).lower() for c in countries],
            allow_amount_max=float(d.get("allow_amount_max", 1000)),
            allow_velocity_max=int(d.get("allow_velocity_max", 10)),
            allow_device_prefix=str(d.get("allow_device_prefix", "dev_known_")),
        )


@dataclass
class AgentConfig:
    """Agent specification from config."""

    agent_id: str
    mission: str
    fallback_rules: FallbackRules

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentConfig":
        fallback_raw = d.get("fallback_rules") or {}
        return cls(
            agent_id=str(d.get("agent_id", "fraud_guard_v1")),
            mission=str(d.get("mission", "")).strip() or "You are a fraud analyst for a payment gateway.",
            fallback_rules=FallbackRules.from_dict(fallback_raw),
        )


@dataclass
class ScenarioConfig:
    """Single test scenario from the scenarios section."""

    label: str
    tx_id: str
    context: Dict[str, Any]
    snapshot: Dict[str, Dict[str, Any]]
    expected: str
    drift_attack: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioConfig":
        ctx = d.get("context", {})
        snap_raw = d.get("snapshot", {})
        snapshot: Dict[str, Dict[str, Any]] = {}
        for user_id, state in snap_raw.items():
            snapshot[str(user_id)] = {str(k): v for k, v in state.items()}
        return cls(
            label=str(d["label"]),
            tx_id=str(d["tx_id"]),
            context={str(k): v for k, v in ctx.items()},
            snapshot=snapshot,
            expected=str(d["expected"]).upper(),
            drift_attack=bool(d.get("drift_attack", False)),
        )


@dataclass
class AppConfig:
    """Full parsed configuration for the Fraud Gate demo."""

    llm: Optional[LlmConfig]
    agent: AgentConfig
    global_max_limit: float
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

    # LLM defaults (optional - use MockLLM if provider=mock or section absent)
    llm = None
    llm_cfg = raw.get("llm_defaults") or {}
    if llm_cfg and str(llm_cfg.get("provider", "")).lower() != "mock":
        llm = LlmConfig.from_dict(llm_cfg)

    # Agent
    agent_cfg = raw.get("agent", {})
    agent = AgentConfig.from_dict(agent_cfg)

    # JIT Validator
    jit_cfg = raw.get("jit_validator", {})
    global_max_limit = float(jit_cfg.get("global_max_limit", 50_000.0))

    # Scenarios
    scenarios_raw = raw.get("scenarios", [])
    scenarios = [ScenarioConfig.from_dict(s) for s in scenarios_raw]

    return AppConfig(
        llm=llm,
        agent=agent,
        global_max_limit=global_max_limit,
        scenarios=scenarios,
    )
