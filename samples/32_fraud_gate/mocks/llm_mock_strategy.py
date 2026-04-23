"""
Deterministic ``MockLLMClient`` strategy for ROA Explain / Policy prompts.

No network; mirrors ``fraud_gate.fallback_rules`` thresholds from config.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from schemas import FallbackRules

logger = logging.getLogger(__name__)


def _parse_tx_from_prompt(prompt: str) -> tuple[float, str, str, int]:
    amount = 0.0
    geo = ""
    device = ""
    velocity = 0
    m = re.search(r"(?:^|\n)amount=([\d.]+)", prompt, re.I)
    if m:
        try:
            amount = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"(?:^|\n)geo_country=(\w+)", prompt, re.I)
    if m:
        geo = m.group(1).lower()
    m = re.search(r"(?:^|\n)device_id=(\S+)", prompt, re.I)
    if m:
        device = m.group(1)
    m = re.search(r"(?:^|\n)velocity_24h=(\d+)", prompt, re.I)
    if m:
        try:
            velocity = int(m.group(1))
        except ValueError:
            pass
    return amount, geo, device, velocity


def _policy_from_rules(
    rules: FallbackRules,
    amount: float,
    geo: str,
    device: str,
    velocity: int,
) -> dict[str, object]:
    if amount > rules.block_amount_threshold and geo in rules.block_high_risk_countries:
        return {
            "proposed_action": "BLOCK",
            "justification": "Mock: high amount in listed high-risk country.",
            "confidence": 0.99,
            "reason_code": "HIGH_RISK_GEO_AMOUNT",
            "risk_score": 0.99,
        }
    if (
        amount < rules.allow_amount_max
        and device.startswith(rules.allow_device_prefix)
        and velocity < rules.allow_velocity_max
    ):
        return {
            "proposed_action": "ALLOW",
            "justification": "Mock: low amount, known device, low velocity.",
            "confidence": 0.9,
            "reason_code": "LOW_RISK_LEGIT",
            "risk_score": 0.1,
        }
    if amount < rules.allow_amount_max:
        return {
            "proposed_action": "ALLOW",
            "justification": "Mock: small amount path.",
            "confidence": 0.85,
            "reason_code": "LOW_RISK_SNAPSHOT",
            "risk_score": 0.15,
        }
    return {
        "proposed_action": "CHALLENGE",
        "justification": "Mock: uncertain band.",
        "confidence": 0.5,
        "reason_code": "UNCERTAIN",
        "risk_score": 0.5,
    }


def make_mock_strategy(
    rules: FallbackRules,
) -> Callable[[str, Optional[str]], str]:
    """Build ``(prompt, system) -> str`` for :class:`shared.llm.clients.MockLLMClient`."""

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        if "ROA_EXPLAIN" in prompt:
            out = {
                "narrative": (
                    "Mock explain: deterministic summary of listed transaction fields."
                ),
                "identified_signals": ["mock_deterministic_explain"],
                "risks": [],
                "opportunities": [],
            }
            response = json.dumps(out)
            logger.debug("[fraud mock] EXPLAIN: %s", response)
            return response

        if "ROA_POLICY" in prompt:
            amount, geo, device, velocity = _parse_tx_from_prompt(prompt)
            out = _policy_from_rules(rules, amount, geo, device, velocity)
            response = json.dumps(out)
            logger.info("[fraud mock] POLICY: %s", response)
            return response

        amount, geo, device, velocity = _parse_tx_from_prompt(prompt)
        if amount == 0.0 and "Amount:" in prompt:
            m = re.search(r"Amount:\s*\$?([\d,]+(?:\.\d+)?)", prompt, re.I)
            if m:
                try:
                    amount = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            m = re.search(r"Country:\s*(\w+)", prompt, re.I)
            if m:
                geo = m.group(1).lower()
            m = re.search(r"Device:\s*(\S+)", prompt, re.I)
            if m:
                device = m.group(1)
            m = re.search(r"last 24h:\s*(\d+)", prompt, re.I)
            if m:
                try:
                    velocity = int(m.group(1))
                except ValueError:
                    pass
        legacy = _policy_from_rules(rules, amount, geo, device, velocity)
        legacy_out = {
            "action": legacy["proposed_action"],
            "reason_code": legacy["reason_code"],
            "risk_score": legacy["risk_score"],
        }
        response = json.dumps(legacy_out)
        logger.info("[fraud mock] legacy single-shot: %s", response)
        return response

    return strategy
