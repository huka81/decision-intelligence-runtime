"""Test doubles for sample 36 — deterministic mock LLM only.

Exports:
  ``make_mock_strategy`` — returns ``(prompt, system) -> str`` JSON for Explain and Policy phases.
"""

from .llm_mock_strategy import make_mock_strategy

__all__ = ["make_mock_strategy"]
