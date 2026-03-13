"""
LLM client for Digital Underwriter ROA agent: Ollama (from utils) and MockLLM.

Usage:
  client = OllamaClient(model="gemma3:4b", base_url="http://localhost:11434")
  text = client.generate("Analyze this application...", system="You are an underwriter.")

MockLLM: USE_MOCK_LLM=1 for tests without Ollama. Returns structured underwriting output.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from utils.ollama_client import LLMClient, OllamaClient

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "OllamaClient", "MockLLM"]


class MockLLM(LLMClient):
    """
    Returns structured underwriting responses for Explain and Policy.
    Use when Ollama is not running or for fast tests.
    Extracts industry from prompt (context) to simulate real LLM behavior.
    """

    def __init__(
        self,
        coverage_limit: Optional[float] = None,
        premium: Optional[float] = None,
        industry_override: Optional[str] = None,
    ):
        """
        Args:
            coverage_limit: Fixed coverage (else computed from revenue in prompt).
            premium: Fixed premium (else ~2% of coverage).
            industry_override: Override industry (else extracted from prompt).
        """
        self.coverage_limit = coverage_limit
        self.premium = premium
        self.industry_override = industry_override

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        prompt_lower = prompt.lower()
        # Policy-style: COVERAGE_LIMIT, PREMIUM, INDUSTRY
        if (
            "coverage_limit" in prompt_lower
            or "premium" in prompt_lower
            or "output format" in prompt_lower
            or "choose coverage" in prompt_lower
        ):
            industry = self.industry_override
            if industry is None:
                # Prefer industry=Value (from context) over industry: Value
                m = re.search(r"industry\s*=\s*(\w+)", prompt_lower, re.I)
                if not m:
                    m = re.search(r"industry[:\s]+(\w+)(?:\s|$)", prompt_lower, re.I)
                industry = m.group(1).strip().title() if m else "Retail"
            revenue = 500_000
            m = re.search(r"revenue[:\s]+([\d.]+)", prompt_lower, re.I)
            if m:
                try:
                    revenue = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            coverage = self.coverage_limit
            if coverage is None:
                coverage = min(revenue * 2, 2_000_000)
            premium = self.premium
            if premium is None:
                premium = coverage * 0.02
            response = (
                f"COVERAGE_LIMIT: {coverage}\n"
                f"PREMIUM: {premium}\n"
                f"INDUSTRY: {industry}\n"
                f"JUSTIFICATION: Mock policy per mission.\n"
                f"CONFIDENCE: 0.85"
            )
            logger.info(
                "MockLLM response (policy): coverage=%.0f, premium=%.0f, industry=%s",
                coverage, premium, industry,
            )
            return response
        # Explain-style
        response = (
            "Narrative: Client application reviewed. "
            "SIGNALS: revenue, industry, business_type. "
            "RISKS: industry risk profile. OPPORTUNITIES: standard underwriting."
        )
        logger.info("MockLLM response (explain)")
        return response
