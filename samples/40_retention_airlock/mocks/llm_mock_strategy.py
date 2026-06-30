"""Deterministic mock LLM for retention ROA without API keys."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def _parse_token(prompt: str, key: str) -> Optional[str]:
    m = re.search(rf"{key}=([^\n]+)", prompt)
    return m.group(1).strip() if m else None


def _parse_multiline_token(prompt: str, key: str) -> str:
    m = re.search(rf"{key}=([\s\S]*)", prompt)
    if not m:
        return ""
    block = m.group(1)
    next_key = re.search(r"\n[A-Z_]+=", block)
    if next_key:
        block = block[: next_key.start()]
    return block.strip()


def _parse_int_token(prompt: str, key: str, default: int) -> int:
    raw = _parse_token(prompt, key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_float_token(prompt: str, key: str, default: float) -> float:
    raw = _parse_token(prompt, key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def make_mock_strategy() -> Any:
    """Returns ``Callable[[str, Optional[str]], str]`` for ``setup_environment``."""

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        phase = (_parse_token(prompt, "PHASE") or "policy").lower()
        policy_kind = _parse_token(prompt, "MOCK_POLICY_KIND") or "APPLY_DISCOUNT"
        discount = _parse_float_token(prompt, "MOCK_DISCOUNT_PCT", 10.0)
        label = _parse_token(prompt, "SCENARIO_LABEL") or ""
        retry_attempt = _parse_int_token(prompt, "RETRY_ATTEMPT", 0)
        prior_trace = _parse_multiline_token(prompt, "PRIOR_FAILURE_TRACE")

        if phase == "explain":
            if "compliant_lie" in label:
                narrative = (
                    "Customer language signals churn risk; retention KPI favors a concession "
                    "even though cancellation wording is present."
                )
            elif "efficiency_trap" in label:
                if prior_trace:
                    narrative = (
                        "Prior DIM rejections are visible in context; agent re-reads failure "
                        "trace and still recommends an aggressive concession without tier lookup."
                    )
                else:
                    narrative = (
                        "High churn risk detected; model recommends an aggressive concession "
                        "without querying external tier limits."
                    )
            elif "compression_drift" in label:
                narrative = (
                    "Customer signals team-wide vendor migration risk alongside support "
                    "and pricing dissatisfaction; retention lever is a policy-compliant discount."
                )
            else:
                narrative = (
                    "Customer cites pricing pressure; a moderate retention discount "
                    "may preserve subscription revenue."
                )
            return json.dumps(
                {
                    "narrative": narrative,
                    "identified_signals": ["pricing_pressure", "retention_lever_available"],
                    "risks": ["margin_compression"],
                    "opportunities": ["retain_mrr"],
                }
            )

        params: Dict[str, Any] = {}
        if policy_kind == "APPLY_DISCOUNT":
            params["discount_pct"] = discount
        elif policy_kind == "CANCEL_SUBSCRIPTION":
            params["immediate"] = True

        justification = (
            f"Propose {policy_kind} aligned with retention mission "
            f"(scenario={label or 'default'})."
        )
        if phase == "policy" and retry_attempt > 0 and prior_trace:
            trace_excerpt = prior_trace.replace("\n", " ")[:160]
            justification = (
                f"Retry {retry_attempt + 1}: re-issued policy after prior_failure_trace "
                f"({trace_excerpt}...); still proposing {discount:.0f}% discount."
            )

        return json.dumps(
            {
                "policy_kind": policy_kind,
                "params": params,
                "justification": justification,
                "confidence": 0.92,
            }
        )

    return strategy
