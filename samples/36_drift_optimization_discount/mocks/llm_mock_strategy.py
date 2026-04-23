"""Deterministic mock LLM for retention ROA (Explain / Policy) without API keys."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def _parse_phase(prompt: str) -> str:
    m = re.search(r"PHASE=(\w+)", prompt)
    return (m.group(1) if m else "policy").lower()


def _parse_discount_hint(prompt: str) -> Optional[float]:
    m = re.search(r"DISCOUNT_HINT=([0-9.+-eE]+)", prompt)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def make_mock_strategy() -> Any:
    """Returns ``Callable[[str, Optional[str]], str]`` for ``setup_environment``."""

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        phase = _parse_phase(prompt)
        hint = _parse_discount_hint(prompt)
        d = float(hint) if hint is not None else 5.0

        if phase == "explain":
            out: Dict[str, Any] = {
                "narrative": (
                    "Subscriber is at risk of churn; retention lever is a time-limited discount. "
                    "Cohort simulator recommends a concession within policy bounds."
                ),
                "identified_signals": ["cancellation_intent", "discount_eligible_plan"],
                "risks": ["margin_compression_if_concession_too_high"],
                "opportunities": ["retain_mrr_if_offer_accepted"],
            }
            return json.dumps(out)

        return json.dumps(
            {
                "policy_kind": "retention_discount",
                "params": {"discount_offered": d},
                "justification": (
                    f"Apply retention_discount with discount_offered={d:.2f}% "
                    "(simulator-aligned; self-check enforces contract)."
                ),
                "confidence": 0.95,
            }
        )

    return strategy
