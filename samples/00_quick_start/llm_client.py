"""
LLM client for 00_quick_start agent: OllamaClient and MockLLM.

Mirrors the pattern from samples/32_fraud_gate/llm_client.py.

MockLLM: deterministic mock for tests without Ollama (USE_MOCK_LLM=1 or provider: mock).
It mimics how a real LLM would naively parse the ambiguous "15,500" feed value
by stripping commas (treating the comma as a thousands separator) → 15500.0.
This reproduces the "Comma Catastrophe" without requiring a live LLM server.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from dir_core.utils.llm_client import LLMClient
from shared.llm.clients import OllamaClient  # re-exported for callers

__all__ = ["LLMClient", "OllamaClient", "MockLLM"]

logger = logging.getLogger(__name__)


class MockLLM(LLMClient):
    """
    Deterministic mock trading agent — no Ollama required.

    Reads ``suggested_position_eth`` from the prompt text and strips commas
    before converting to float.  This is the same naive parsing a real LLM
    would apply to a locale-ambiguous string like "15,500", turning it into
    15500.0 instead of the intended 15.5 — the "Comma Catastrophe".
    For clean values (e.g. "0.5") the result is correct.
    """

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        # Extract suggested_position_eth
        m = re.search(r'suggested_position_eth["\']?\s*:\s*["\']?([\d,\.]+)', prompt, re.I)
        quantity = 0.0
        if m:
            raw = m.group(1).strip()
            try:
                # Strip commas — naive locale-agnostic parsing (reproduces the mistake)
                quantity = float(raw.replace(",", ""))
            except ValueError:
                quantity = 0.0

        # Extract instrument
        m_inst = re.search(r'instrument["\']?\s*:\s*["\']?([\w\-]+)', prompt, re.I)
        instrument = m_inst.group(1) if m_inst else "ETH-USD"

        return json.dumps({
            "policy_kind": "BUY",
            "params": {
                "instrument": instrument,
                "quantity": quantity,
                "execution_type": "MARKET",
            },
            "justification": "Strong momentum signal from feed; increasing ETH exposure.",
            "confidence": 0.92,
        })
