"""
LLM client for Digital Underwriter ROA agent: Ollama (from dir_core.utils) and MockLLM.

Usage:
  client = OllamaClient(model="gemma3:4b", base_url="http://localhost:11434")
  text = client.generate("Analyze this application...", system="You are an underwriter.")

MockLLM: USE_MOCK_LLM=1 for tests without Ollama. Returns structured underwriting output.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from dir_core.utils.llm_client import LLMClient, OllamaClient

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "OllamaClient", "MockLLM"]


def _mock_territory_row_text(body: str) -> str:
    """Collect Territory table row cells (renewal + remarks columns) for mock extraction."""
    for line in body.splitlines():
        if not re.match(r"^\|\s*Territory\s*\|", line, re.I):
            continue
        parts = [p.strip() for p in line.split("|")]
        inner = [p for p in parts if p]
        if not inner:
            continue
        if inner[0].lower().replace(" ", "") == "territory":
            cells = inner[1:]
        else:
            cells = inner
        if cells:
            return "; ".join(cells)
    return "Not stated"


def _mock_tiv_usd_from_body(body: str, fx: dict[str, float]) -> float:
    """TiV from | Total Insurable Values | row (Total: **CUR n** or **CUR n**)."""
    for line in body.splitlines():
        if not re.match(r"^\|\s*Total\s+Insurable\s+Values\s*\|", line, re.I):
            continue
        tot_pairs = re.findall(
            r"\*\*Total:\s*(GBP|USD|EUR)\s*([\d_,]+(?:\.\d+)?)\*\*",
            line,
            re.I,
        )
        if tot_pairs:
            cur, raw_amt = tot_pairs[-1]
            return float(raw_amt.replace(",", "")) * fx.get(cur.upper(), 1.0)
        pairs = re.findall(
            r"\*\*(GBP|USD|EUR)\s*([\d_,]+(?:\.\d+)?)\*\*",
            line,
            re.I,
        )
        if pairs:
            cur, raw_amt = pairs[-1]
            return float(raw_amt.replace(",", "")) * fx.get(cur.upper(), 1.0)
    raise ValueError(
        "MockLLM: no TiV figure in Total Insurable Values table row",
    )


def _mock_extract_submission_facts(user_prompt: str, system: Optional[str]) -> str:
    """Deterministic TiV + territory extraction for tests (mirrors agent task)."""
    body = user_prompt
    if "EMAIL:" in user_prompt:
        body = user_prompt.split("EMAIL:", 1)[-1].lstrip()

    fx: dict[str, float] = {"GBP": 1.0, "USD": 1.0, "EUR": 1.0}
    if system:
        mj = re.search(r"FX_MAP_JSON:\s*(\{[^\n]+\})", system)
        if mj:
            try:
                raw = json.loads(mj.group(1))
                fx = {str(k).upper(): float(v) for k, v in raw.items()}
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    usd = _mock_tiv_usd_from_body(body, fx)
    stated = _mock_territory_row_text(body)
    out = (
        f"BROKER_REQUESTED_TIV_USD: {usd}\n"
        f"STATED_TERRITORIES: {stated}"
    )
    logger.info("MockLLM response (extract facts): %s", out.replace("\n", " | "))
    return out


class MockLLM(LLMClient):
    """
    Returns structured underwriting responses for Explain and Policy.
    Use when Ollama is not running or for fast tests.
    Extracts industry from prompt (context) to simulate real LLM behavior.
    """

    def __init__(
        self,
        total_insured_value: Optional[float] = None,
        premium: Optional[float] = None,
        industry_override: Optional[str] = None,
    ):
        """
        Args:
            total_insured_value: Fixed TiV (else from broker_requested_tiv_usd or revenue).
            premium: Fixed premium (else ~2% of TiV).
            industry_override: Override industry (else extracted from prompt).
        """
        self.total_insured_value = total_insured_value
        self.premium = premium
        self.industry_override = industry_override

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        prompt_lower = prompt.lower()
        if system and "TASK: EXTRACT_SUBMISSION_FACTS" in system:
            return _mock_extract_submission_facts(prompt, system)
        # Policy stage always includes "Interpretation:"; Explain uses "Client application:".
        if "interpretation:" in prompt_lower:
            sys = system or ""
            max_tiv = 2_000_000
            mm = re.search(
                r"max total insured value \(tiv\):\s*([\d_,]+)",
                sys.lower(),
            )
            if mm:
                try:
                    max_tiv = float(mm.group(1).replace(",", ""))
                except ValueError:
                    pass
            industry = self.industry_override
            if industry is None:
                m = re.search(r"industry_label:\s*([^\n]+)", prompt_lower, re.I)
                if not m:
                    m = re.search(r"industry\s*=\s*([^\n]+)", prompt_lower, re.I)
                if not m:
                    m = re.search(r"industry[:\s]+(\w+)(?:\s|$)", prompt_lower, re.I)
                industry = (m.group(1).strip() if m else "Retail")[:200]
            revenue = 500_000
            m = re.search(r"revenue[:\s]+([\d.]+)", prompt_lower, re.I)
            if m:
                try:
                    revenue = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            requested = None
            m = re.search(
                r"broker_requested_tiv_usd[:\s]+([\d.]+)",
                prompt_lower,
                re.I,
            )
            if m:
                try:
                    requested = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            tiv = self.total_insured_value
            if tiv is None:
                if requested is not None:
                    tiv = min(requested, max_tiv)
                else:
                    tiv = min(revenue * 2, max_tiv)
            premium = self.premium
            if premium is None:
                premium = tiv * 0.02
            response = (
                f"TOTAL_INSURED_VALUE: {tiv}\n"
                f"PREMIUM: {premium}\n"
                f"INDUSTRY: {industry}\n"
                f"JUSTIFICATION: Mock policy per mission.\n"
                f"CONFIDENCE: 0.85"
            )
            logger.info(
                "MockLLM response (policy): tiv=%.0f, premium=%.0f, industry=%s",
                tiv, premium, industry,
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
