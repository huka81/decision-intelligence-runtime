"""Deterministic LLM mock for credit-limit ROA cycle."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional


def make_mock_strategy(
    *,
    drift_iteration: Optional[int] = None,
    drift_config: Optional[Dict[str, Any]] = None,
) -> Callable[[str, Optional[str]], str]:
    """Return a mock LLM callable for setup_environment."""

    def _strategy(prompt: str, system: Optional[str] = None) -> str:
        if drift_iteration is not None and drift_config is not None:
            return _drift_response(drift_iteration, drift_config, prompt)

        if "explain" in prompt.lower() or "narrative" in prompt.lower():
            return (
                "Customer requests a credit limit increase. "
                "Chat states monthly income and desired new limit."
            )

        income = 4000
        limit = 8000
        justification = (
            "Declared income supports debt-to-income ratio for limit increase."
        )

        if "30000" in prompt or "3000 pln" in prompt.lower():
            income = 30000
            limit = 8000

        if "threatened to cancel" in prompt.lower() or "proxy" in prompt.lower():
            justification = (
                "User threatened to cancel card; approved limit to reduce churn risk "
                "despite borderline income."
            )

        return json.dumps(
            {
                "policy_kind": "RAISE_LIMIT",
                "params": {
                    "customer_id": "cust_mock",
                    "declared_income_pln": income,
                    "requested_limit_pln": limit,
                    "current_limit_pln": 5000,
                },
                "confidence": 0.9,
                "justification": justification,
            }
        )

    return _strategy


def _drift_response(
    iteration: int,
    drift_config: Dict[str, Any],
    prompt: str,
) -> str:
    phase1 = int(drift_config.get("phase1_iterations", 5))
    if iteration <= phase1:
        income = float(drift_config.get("phase1_income_pln", 4000))
        limit = float(drift_config.get("phase1_limit_pln", 8000))
    else:
        income = float(drift_config.get("phase2_income_pln", 2200))
        limit = float(drift_config.get("phase2_limit_pln", 9000))

    phrase = str(drift_config.get("priority_article_phrase", ""))
    if "explain" in prompt.lower():
        return f"Drift batch iteration {iteration}. Chat includes: {phrase}"

    return json.dumps(
        {
            "policy_kind": "RAISE_LIMIT",
            "params": {
                "customer_id": f"drift_cust_{iteration:02d}",
                "declared_income_pln": income,
                "requested_limit_pln": limit,
                "current_limit_pln": 5000,
            },
            "confidence": 0.85,
            "justification": f"Priority article phrase acknowledged. Income {income} PLN.",
        }
    )
