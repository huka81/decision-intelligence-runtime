"""
``32_fraud_gate`` domain shapes, scenario rows, and config slices (Sample Guide §3, §8).

- Pydantic models for transaction input and illustrative grammar types.
- Dataclasses: ``FallbackRules``, ``ScenarioConfig``.
- ``load_scenarios()`` — default path ``scenarios.yaml`` next to this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from shared.config import load_yaml_config

# --- Pydantic (LLM / transaction surface) ---------------------------------


class FraudDecisionSchema(BaseModel):
    """Straightjacket grammar for structured fraud labels (illustrative)."""

    action: Literal["ALLOW", "BLOCK", "CHALLENGE"]
    reason_code: str
    risk_score: float = Field(ge=0.0, le=1.0)


class TransactionContext(BaseModel):
    """Transaction context passed to the ROA agent."""

    user_id: str
    amount: float
    geo_country: str
    device_id: str
    velocity_24h: int


class DecisionAtom(FraudDecisionSchema):
    """Decision with snapshot binding (illustrative type)."""

    snapshot_id: str = Field(
        description="Context snapshot hash for JIT drift check",
    )
    dfid: str = Field(description="DecisionFlow ID for correlation")
    user_id: str = Field(description="User ID for risk cache lookup")
    amount: float = Field(
        description="Transaction amount for hard limit check",
    )


# --- Config slices (from ``config.yaml`` dict) ----------------------------


@dataclass
class FallbackRules:
    """Thresholds shared by mock strategy and agent fallback."""

    block_amount_threshold: float
    block_high_risk_countries: List[str]
    allow_amount_max: float
    allow_velocity_max: int
    allow_device_prefix: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FallbackRules":
        countries = d.get("block_high_risk_countries", ["nigeria"])
        return cls(
            block_amount_threshold=float(
                d.get("block_amount_threshold", 5000),
            ),
            block_high_risk_countries=[str(c).lower() for c in countries],
            allow_amount_max=float(d.get("allow_amount_max", 1000)),
            allow_velocity_max=int(d.get("allow_velocity_max", 10)),
            allow_device_prefix=str(
                d.get("allow_device_prefix", "dev_known_"),
            ),
        )


def fallback_rules_from_config(config: Dict[str, Any]) -> FallbackRules:
    raw = (config.get("fraud_gate") or {}).get("fallback_rules") or {}
    return FallbackRules.from_dict(raw)


def global_max_limit_from_config(config: Dict[str, Any]) -> float:
    jit_cfg = config.get("jit_validator") or {}
    return float(jit_cfg.get("global_max_limit", 50_000.0))


# --- Scenario fixtures (``scenarios.yaml``) ------------------------------


@dataclass
class ScenarioConfig:
    """Single row from ``scenarios.yaml``."""

    label: str
    tx_id: str
    context: Dict[str, Any]
    snapshot: Dict[str, Dict[str, Any]]
    expected: str
    drift_attack: bool = False
    notes: str = ""

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
            notes=str(d.get("notes", "")),
        )


_DEFAULT_SCENARIOS = Path(__file__).parent / "scenarios.yaml"


def load_scenarios(path: Optional[Path] = None) -> List[ScenarioConfig]:
    """Load ``scenarios.yaml`` and return typed scenario rows (§8)."""
    config_path = Path(path) if path else _DEFAULT_SCENARIOS
    raw = load_yaml_config(config_path)
    items = raw.get("scenarios")
    if not isinstance(items, list):
        raise ValueError(
            "scenarios.yaml must contain a top-level 'scenarios' list "
            f"({config_path})"
        )
    return [ScenarioConfig.from_dict(s) for s in items]
