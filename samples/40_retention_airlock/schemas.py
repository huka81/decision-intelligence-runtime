"""Domain shapes, scenario rows, and config slices for 40_retention_airlock."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from shared.config import load_yaml_config

ExpectedVerdict = Literal["ACCEPT", "REJECT", "ESCALATE", "SUSPENDED"]


@dataclass
class BidirectionalReconstructionConfig:
    min_keyword_overlap: float
    salient_terms: List[str]

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "BidirectionalReconstructionConfig":
        raw = (config.get("retention_airlock") or {}).get("bidirectional_reconstruction") or {}
        terms = [str(t).lower() for t in (raw.get("salient_terms") or ["team", "vendor"])]
        return cls(
            min_keyword_overlap=float(raw.get("min_keyword_overlap", 0.25)),
            salient_terms=terms,
        )


@dataclass
class RetentionAirlockConfig:
    tier_discount_limits: Dict[str, float]
    retention_actions: List[str]
    cancel_intent_patterns: List[str]
    intent_retry_max: int
    bidirectional: BidirectionalReconstructionConfig

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RetentionAirlockConfig":
        raw = config.get("retention_airlock") or {}
        limits_raw = raw.get("tier_discount_limits") or {"BASIC": 15.0}
        limits = {str(k).upper(): float(v) for k, v in limits_raw.items()}
        actions = [str(a) for a in (raw.get("retention_actions") or ["APPLY_DISCOUNT"])]
        patterns = [str(p).lower() for p in (raw.get("cancel_intent_patterns") or [])]
        retry_raw = raw.get("intent_retry") or {}
        return cls(
            tier_discount_limits=limits,
            retention_actions=actions,
            cancel_intent_patterns=patterns,
            intent_retry_max=int(retry_raw.get("max_retries", 3)),
            bidirectional=BidirectionalReconstructionConfig.from_config(config),
        )


@dataclass
class TemporalMonitorConfig:
    window_size: int
    avg_threshold_pct: float
    suspension_reason: str

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "TemporalMonitorConfig":
        raw = config.get("temporal_monitor") or {}
        return cls(
            window_size=int(raw.get("window_size", 7)),
            avg_threshold_pct=float(raw.get("avg_threshold_pct", 14.5)),
            suspension_reason=str(raw.get("suspension_reason", "MARGIN_EROSION_DRIFT")),
        )


@dataclass
class DriftSweepConfig:
    enabled: bool
    iterations: int
    customer_id: str
    customer_tier: str
    email_template: str
    mock_discount_pct: float

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "DriftSweepConfig":
        raw = config.get("drift_sweep") or {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            iterations=int(raw.get("iterations", 10)),
            customer_id=str(raw.get("customer_id", "cust-4004")),
            customer_tier=str(raw.get("customer_tier", "BASIC")).upper(),
            email_template=str(raw.get("email_template", "")),
            mock_discount_pct=float(raw.get("mock_discount_pct", 15.0)),
        )


@dataclass
class ScenarioConfig:
    label: str
    customer_id: str
    customer_tier: str
    email_body: str
    mock_policy_kind: str
    mock_discount_pct: float
    expected: ExpectedVerdict
    retry_until_exhaustion: bool = False
    expected_terminal_reason: str = ""
    enable_bidirectional_reconstruction: bool = False
    notes: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioConfig":
        return cls(
            label=str(d["label"]),
            customer_id=str(d["customer_id"]),
            customer_tier=str(d.get("customer_tier", "BASIC")).upper(),
            email_body=str(d.get("email_body", "")),
            mock_policy_kind=str(d.get("mock_policy_kind", "APPLY_DISCOUNT")),
            mock_discount_pct=float(d.get("mock_discount_pct", 10.0)),
            expected=str(d["expected"]).upper(),  # type: ignore[arg-type]
            retry_until_exhaustion=bool(d.get("retry_until_exhaustion", False)),
            expected_terminal_reason=str(d.get("expected_terminal_reason", "")),
            enable_bidirectional_reconstruction=bool(
                d.get("enable_bidirectional_reconstruction", False)
            ),
            notes=str(d.get("notes", "")),
        )


@dataclass
class ContextTaxAttempt:
    attempt: int
    estimated_tokens: int
    prior_failure_trace: str = ""


@dataclass
class ScenarioResult:
    label: str
    dfid: str
    expected: str
    final_verdict: str
    dim_reason: str
    executed: bool
    retry_count: int = 0
    airlock_trace: Dict[str, str] = field(default_factory=dict)
    explain_narrative: str = ""
    justification: str = ""
    policy_kind: str = ""
    discount_pct: float = 0.0
    escalated: bool = False
    reconstructed_narrative: str = ""
    keyword_overlap: float = 0.0
    context_tax_attempts: List["ContextTaxAttempt"] = field(default_factory=list)
    email_body: str = ""


@dataclass
class DriftSweepResult:
    steps: List[ScenarioResult] = field(default_factory=list)
    suspended: bool = False
    suspension_iteration: Optional[int] = None
    stopped_reason: str = ""


_DEFAULT_SCENARIOS = Path(__file__).parent / "scenarios.yaml"


def load_scenarios(path: Optional[Path] = None) -> List[ScenarioConfig]:
    config_path = Path(path) if path else _DEFAULT_SCENARIOS
    raw = load_yaml_config(config_path)
    items = raw.get("scenarios")
    if not isinstance(items, list):
        raise ValueError(
            f"scenarios.yaml must contain a top-level 'scenarios' list ({config_path})"
        )
    return [ScenarioConfig.from_dict(s) for s in items]


def load_sample_config(sample_dir: Path) -> Dict[str, Any]:
    return load_yaml_config(sample_dir / "config.yaml")


def max_discount_for_tier(airlock: RetentionAirlockConfig, tier: str) -> float:
    return float(airlock.tier_discount_limits.get(tier.upper(), 15.0))
