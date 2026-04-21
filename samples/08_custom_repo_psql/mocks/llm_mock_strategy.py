"""Deterministic LLM for USE_MOCK_LLM=1 — covers Explain and Policy prompt shapes."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional


def make_mock_strategy(config: Dict[str, Any]) -> Callable[[str, Optional[str]], str]:
    """Return JSON for ROA Explain and Policy stages (Sample Guide §12)."""

    seeds = (config.get("simulation") or {}).get("seeds") or {}
    _ = int(seeds.get("mock_llm", 42))

    def strategy(prompt: str, system: Optional[str] = None) -> str:
        _ = system
        if "[DIR_ROA_EXPLAIN]" in prompt:
            return json.dumps(
                {
                    "narrative": "Demo input describes a PostgreSQL-backed run; no action.",
                    "signals": ["repo_demo"],
                    "risks": [],
                    "opportunities": [],
                }
            )
        return json.dumps(
            {
                "policy_kind": "HOLD",
                "params": {},
                "justification": "Mock: infrastructure sample — hold.",
                "confidence": 0.95,
            }
        )

    return strategy
