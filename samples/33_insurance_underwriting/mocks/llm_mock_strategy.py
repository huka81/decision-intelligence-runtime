"""Deterministic mock LLM for underwriting — no API key (Sample Guide §12)."""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _mock_territory_row_text(body: str) -> str:
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
        "Mock strategy: no TiV figure in Total Insurable Values table row",
    )


def _mock_extract_submission_facts(user_prompt: str, system: Optional[str]) -> str:
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
    out = f"BROKER_REQUESTED_TIV_USD: {usd}\nSTATED_TERRITORIES: {stated}"
    logger.info("Mock LLM (extract facts): %s", out.replace("\n", " | "))
    return out


def make_mock_strategy() -> Callable[[str, Optional[str]], str]:
    """Return ``generate``-compatible strategy for ``MockLLMClient``."""

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        if system and "TASK: EXTRACT_SUBMISSION_FACTS" in system:
            return _mock_extract_submission_facts(prompt, system)
        prompt_lower = prompt.lower()
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
            industry = None
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
            if requested is not None:
                tiv = min(requested, max_tiv)
            else:
                tiv = min(revenue * 2, max_tiv)
            premium = tiv * 0.02
            response = (
                f"TOTAL_INSURED_VALUE: {tiv}\n"
                f"PREMIUM: {premium}\n"
                f"INDUSTRY: {industry}\n"
                f"JUSTIFICATION: Mock policy per mission.\n"
                f"CONFIDENCE: 0.85"
            )
            logger.info(
                "Mock LLM (policy): tiv=%.0f, premium=%.0f, industry=%s",
                tiv,
                premium,
                industry,
            )
            return response
        response = (
            "Narrative: Client application reviewed. "
            "SIGNALS: revenue, industry, business_type. "
            "RISKS: industry risk profile. OPPORTUNITIES: standard underwriting."
        )
        logger.info("Mock LLM (explain)")
        return response

    return strategy
