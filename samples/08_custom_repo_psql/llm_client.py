"""
LLM client for 08_custom_repo_psql — OllamaClient and MockLLM.

MockLLM: deterministic mock for tests without Ollama (USE_MOCK_LLM=1 or
provider: mock in config.yaml).

Reproduces the "Comma Catastrophe": the mock naively strips commas from the
feed string "15,500", producing 15500.0 instead of the intended 15.5.
This triggers the DIM ORDER_VALUE_EXCEEDED rejection even without a live LLM.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from dir_core.utils.llm_client import LLMClient, OllamaClient  # re-exported

__all__ = ["LLMClient", "OllamaClient", "MockLLM"]

logger = logging.getLogger(__name__)


class MockLLM(LLMClient):
    """Deterministic mock trading agent — no Ollama required.

    Reads ``suggested_position_eth`` from the prompt text and strips commas
    before converting to float.  Same naive parsing a real LLM would apply to
    a locale-ambiguous string like "15,500" — the "Comma Catastrophe".
    """

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        m = re.search(
            r'suggested_position_eth["\']?\s*:\s*["\']?([\d,\.]+)',
            prompt,
            re.I,
        )
        quantity = 0.0
        if m:
            raw = m.group(1).strip()
            try:
                quantity = float(raw.replace(",", ""))
            except ValueError:
                quantity = 0.0

        m_inst = re.search(
            r'instrument["\']?\s*:\s*["\']?([\w\-]+)', prompt, re.I
        )
        instrument = m_inst.group(1) if m_inst else "ETH-USD"

        return json.dumps(
            {
                "policy_kind": "BUY",
                "params": {
                    "instrument": instrument,
                    "quantity": quantity,
                    "execution_type": "MARKET",
                },
                "justification": (
                    "Strong momentum signal from feed; increasing ETH exposure."
                ),
                "confidence": 0.92,
            }
        )
