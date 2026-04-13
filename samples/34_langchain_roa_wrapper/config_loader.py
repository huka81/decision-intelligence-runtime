"""
34_langchain_roa_wrapper - Configuration loader for config.yaml.

Loads and validates the YAML config, building typed objects used by run.py:
  - LlmConfig      : LLM provider settings (model, base_url, temperature)
  - FinOpsContract : Agent responsibility contract (allowed_environments, etc.)
  - context_store  : Authoritative infrastructure state for DIM validation
  - scenarios      : List of test scenario dicts with idle_resources and expected verdicts

Usage:
    cfg = load_config()                         # loads config.yaml next to this file
    cfg = load_config("path/to/config.yaml")    # explicit path

Same pattern as 35_crewai_roa_wrapper config loading.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts import FinOpsContract
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
    idle_resources: Dict[str, Any]
    expected: str
    show_mission_demo: bool = False
    trust_input_labels: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioConfig":
        idle = d.get("idle_resources", {})
        if not isinstance(idle, dict):
            idle = {}
        return cls(
            label=str(d["label"]),
            idle_resources=idle,
            expected=str(d.get("expected", "ACCEPT")).upper(),
            show_mission_demo=bool(d.get("show_mission_demo", False)),
            trust_input_labels=bool(d.get("trust_input_labels", False)),
        )


@dataclass
class AppConfig:
    """Full parsed configuration for the FinOps Agent demo."""

    llm: LlmConfig
    contract: FinOpsContract
    context_store: Dict[str, Any]
    scenarios: List[ScenarioConfig]


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

    # Agent contract
    agent_cfg = raw.get("agent")
    if not agent_cfg:
        raise KeyError("config.yaml missing required section: agent")
    contract = FinOpsContract.from_config(agent_cfg)

    # Context Store - normalise instances
    context_store_raw = raw.get("context_store", {})
    instances_raw = context_store_raw.get("instances", {})
    context_store: Dict[str, Any] = {
        "instances": {
            str(inst_id): {str(k): v for k, v in inst_data.items()}
            for inst_id, inst_data in instances_raw.items()
        }
    }

    # Scenarios
    scenarios_raw = raw.get("scenarios", [])
    scenarios = [ScenarioConfig.from_dict(s) for s in scenarios_raw]

    return AppConfig(
        llm=llm,
        contract=contract,
        context_store=context_store,
        scenarios=scenarios,
    )
