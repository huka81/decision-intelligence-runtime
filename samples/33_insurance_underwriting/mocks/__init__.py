"""
Test doubles for sample 33 — deterministic LLM mock strategy (no live model).

Replaces external LLM calls when ``USE_MOCK_LLM=1`` or ``llm_defaults.provider: mock``.
"""

from .llm_mock_strategy import make_mock_strategy

__all__ = ["make_mock_strategy"]
