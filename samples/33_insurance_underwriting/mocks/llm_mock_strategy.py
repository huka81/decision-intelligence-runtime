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


def _mock_policy_proposal_json(
    user_prompt: str,
    system: Optional[str],
) -> str:
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

    tiv = _mock_tiv_usd_from_body(body, fx)
    territory = _mock_territory_row_text(body)
    payload = {
        "total_insured_value": tiv,
        "territory": territory,
        "justification": "Mock policy per mission.",
    }
    response = json.dumps(payload)
    logger.info(
        "Mock LLM (policy proposal): tiv=%.0f, territory=%s",
        tiv,
        territory[:60],
    )
    return response


def make_mock_strategy() -> Callable[[str, Optional[str]], str]:
    """Return ``generate``-compatible strategy for ``MockLLMClient``."""

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        return _mock_policy_proposal_json(prompt, system)

    return strategy
