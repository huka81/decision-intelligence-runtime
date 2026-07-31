"""Domain and role presets for Bootstrap Contract interview."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PresetDefinition:
    """Default interview values for a domain or role template."""

    name: str
    description: str
    default_role: str = "EXECUTOR"
    required_limit_keys: List[str] = field(default_factory=list)
    suggested_limits: Dict[str, float] = field(default_factory=dict)
    allowed_policy_types: List[str] = field(default_factory=list)
    authorized_instruments: List[str] = field(default_factory=list)
    mission_template: str = ""
    evidence_level: str = "medium"
    escalate_on_uncertainty: float = 0.7


PRESETS: Dict[str, PresetDefinition] = {
    "trading": PresetDefinition(
        name="trading",
        description="Crypto or equities execution with order size and drawdown caps.",
        default_role="EXECUTOR",
        required_limit_keys=["max_order_size_usd", "max_drawdown_limit_pct"],
        suggested_limits={
            "max_order_size_usd": 50_000.0,
            "max_drawdown_limit_pct": 4.0,
        },
        allowed_policy_types=["BUY", "SELL", "HOLD", "CLOSE_POSITION", "REDUCE_SIZE"],
        authorized_instruments=["ETH-USD", "BTC-USD"],
        mission_template=(
            "Execute market orders safely within defined capital and drawdown limits."
        ),
        evidence_level="high",
        escalate_on_uncertainty=0.7,
    ),
    "fraud_gate": PresetDefinition(
        name="fraud_gate",
        description="Payment fraud gate: approve, block, or challenge transactions.",
        default_role="EXECUTOR",
        required_limit_keys=["max_transaction_usd"],
        suggested_limits={"max_transaction_usd": 5_000.0},
        allowed_policy_types=["ALLOW", "BLOCK", "CHALLENGE"],
        authorized_instruments=[],
        mission_template=(
            "Evaluate payment transactions and recommend ALLOW, BLOCK, or CHALLENGE "
            "within transaction exposure limits."
        ),
        evidence_level="high",
        escalate_on_uncertainty=0.35,
    ),
    "underwriting": PresetDefinition(
        name="underwriting",
        description="Insurance underwriting with premium and coverage limits.",
        default_role="EXECUTOR",
        required_limit_keys=["max_premium_usd", "max_limit_usd"],
        suggested_limits={
            "max_premium_usd": 100_000.0,
            "max_limit_usd": 1_000_000.0,
        },
        allowed_policy_types=["QUOTE", "DECLINE", "REFER", "BIND"],
        authorized_instruments=[],
        mission_template=(
            "Underwrite risks within premium and coverage authority; escalate borderline cases."
        ),
        evidence_level="high",
        escalate_on_uncertainty=0.65,
    ),
    "retention_refund": PresetDefinition(
        name="retention_refund",
        description="Customer retention and refund decisions.",
        default_role="EXECUTOR",
        required_limit_keys=["max_refund_usd", "max_discount_pct"],
        suggested_limits={
            "max_refund_usd": 50.0,
            "max_discount_pct": 15.0,
        },
        allowed_policy_types=["REFUND", "DISCOUNT", "DENY", "ESCALATE"],
        authorized_instruments=[],
        mission_template=(
            "Resolve customer complaints with refunds or discounts only within policy limits."
        ),
        evidence_level="medium",
        escalate_on_uncertainty=0.7,
    ),
    "generic": PresetDefinition(
        name="generic",
        description="Domain-agnostic executor; you must name at least one irreversible limit.",
        default_role="EXECUTOR",
        required_limit_keys=[],
        suggested_limits={"max_order_size_usd": 1_000.0},
        allowed_policy_types=["ACTION", "HOLD", "ESCALATE"],
        authorized_instruments=[],
        mission_template="Perform bounded decisions within explicit irreversible limits.",
        evidence_level="medium",
        escalate_on_uncertainty=0.7,
    ),
    "interface_dmz": PresetDefinition(
        name="interface_dmz",
        description="Edge INTERFACE agent with zero execution authority.",
        default_role="INTERFACE",
        required_limit_keys=[],
        allowed_policy_types=[],
        mission_template=(
            "Normalize inbound external payloads; emit bounded input artifacts only."
        ),
        evidence_level="low",
        escalate_on_uncertainty=0.5,
    ),
    "strategist": PresetDefinition(
        name="strategist",
        description="High-level planner delegating to executors.",
        default_role="STRATEGIST",
        required_limit_keys=["max_order_size_usd"],
        suggested_limits={"max_order_size_usd": 100_000.0},
        allowed_policy_types=["DELEGATE", "HOLD", "ESCALATE"],
        mission_template="Synthesize long-horizon context and delegate tactical decisions.",
        evidence_level="medium",
        escalate_on_uncertainty=0.6,
    ),
    "monitor": PresetDefinition(
        name="monitor",
        description="Read-only post-execution auditor; may trigger circuit breakers.",
        default_role="MONITOR",
        required_limit_keys=[],
        allowed_policy_types=["SUSPEND_AGENT", "ALERT", "NOOP"],
        mission_template=(
            "Audit agent explain histories asynchronously; detect drift and trigger breakers."
        ),
        evidence_level="medium",
        escalate_on_uncertainty=0.5,
    ),
}


def get_preset(name: str) -> PresetDefinition:
    return PRESETS.get(name, PRESETS["generic"])


def list_preset_names() -> List[str]:
    return sorted(PRESETS.keys())
