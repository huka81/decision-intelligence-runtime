"""Deterministic tier limits used by Fact Validation (legacy ground truth)."""

from __future__ import annotations

from typing import Dict


def tier_limits_from_config(tier_limits: Dict[str, float]) -> Dict[str, float]:
    return {str(k).upper(): float(v) for k, v in tier_limits.items()}


def max_discount_for_customer(tier: str, tier_limits: Dict[str, float]) -> float:
    return float(tier_limits.get(tier.upper(), 15.0))
