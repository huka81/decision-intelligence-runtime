"""Deterministic MockLLM responses for finance trading ROA agents (Explain / Policy)."""

from __future__ import annotations

from typing import Callable, Optional


def make_mock_strategy() -> Callable[[str, Optional[str]], str]:
    """Return a strategy covering instrument and news agent prompt shapes."""

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        prompt_lower = prompt.lower()
        if (
            "choose one action" in prompt_lower
            or "output action" in prompt_lower
            or "action, justification" in prompt_lower
        ):
            return (
                "ACTION: HOLD\nJUSTIFICATION: Mock policy per mission.\nCONFIDENCE: 0.8"
            )
        if (
            "narrative" in prompt_lower
            or "signals:" in prompt_lower
            or "risks:" in prompt_lower
            or "opportunities:" in prompt_lower
        ):
            return (
                "Narrative: Market context observed. SIGNALS: price_update, trend. "
                "RISKS: volatility. OPPORTUNITIES: trend continuation. "
            )
        return "ACTION: HOLD\nJUSTIFICATION: Mock policy per mission.\nCONFIDENCE: 0.8"

    return strategy
