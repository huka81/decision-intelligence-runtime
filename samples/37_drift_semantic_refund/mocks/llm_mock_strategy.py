"""Deterministic mock LLM for bootstrap when no live model is available."""

from __future__ import annotations

from typing import Callable, Optional


def make_mock_strategy(*, seed: int = 37) -> Callable[..., str]:
    """Return ``mock_llm_strategy`` for ``setup_environment``."""

    def mock_llm_strategy(prompt: str, system: Optional[str] = None) -> str:
        _ = (prompt, system, seed)
        return (
            '{"policy_kind": "REFUND", "params": {"refund_amount_eur": 35.0}, '
            '"justification": "Mock deterministic default.", "confidence": 0.8}'
        )

    return mock_llm_strategy
