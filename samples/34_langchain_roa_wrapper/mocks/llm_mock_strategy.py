"""Deterministic mock LLM for FinOps ROA when ``USE_MOCK_LLM=1`` (Sample Guide §12)."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional


def _policy_from_instances(
    instances: List[Dict[str, Any]],
    trust_input_labels: bool,
) -> Dict[str, Any]:
    """Deterministic policy JSON mimicking LangChain tool output shape."""
    if not instances:
        return {
            "action": "SCALE_DOWN",
            "resource_id": "",
            "reason": "No idle instances in view.",
            "confidence": 0.5,
        }

    if trust_input_labels:
        prod_mislabeled = next(
            (
                i
                for i in instances
                if str(i.get("id", "")) == "i-prod-api-01"
                and str(i.get("environment", "")).upper() == "DEV"
            ),
            None,
        )
        if prod_mislabeled:
            return {
                "action": "TERMINATE",
                "resource_id": "i-prod-api-01",
                "reason": "Mock: trusted input labels; targeting mislabeled instance.",
                "confidence": 0.88,
            }

    ids = {str(i.get("id", "")) for i in instances}
    if "i-dev-worker-03" in ids and "i-prod-api-01" in ids:
        return {
            "action": "TERMINATE",
            "resource_id": "i-dev-worker-03",
            "reason": "Mock: mission prefers non-PROD; DEV instance selected.",
            "confidence": 0.86,
        }
    if "i-dev-worker-03" in ids:
        return {
            "action": "TERMINATE",
            "resource_id": "i-dev-worker-03",
            "reason": "Mock: sole DEV idle instance.",
            "confidence": 0.87,
        }
    first = str(instances[0].get("id", ""))
    return {
        "action": "TERMINATE",
        "resource_id": first,
        "reason": "Mock: default first instance.",
        "confidence": 0.82,
    }


def make_mock_strategy() -> Callable[[str, Optional[str]], str]:
    def strategy(prompt: str, system: Optional[str] = None) -> str:
        if "[FINOPS_EXPLAIN]" in prompt:
            return json.dumps(
                {
                    "narrative": "Idle compute detected; cost reduction possible without PROD touch.",
                    "signals": ["idle_hours_elevated"],
                    "risks": ["Accidental PROD termination"],
                    "opportunities": ["Terminate DEV/STG idle nodes"],
                }
            )
        if "[FINOPS_POLICY]" in prompt:
            m = re.search(
                r"PAYLOAD_JSON\n(\{[\s\S]*\})\s*$",
                prompt.strip(),
            )
            if not m:
                return json.dumps(
                    {
                        "action": "SCALE_DOWN",
                        "resource_id": "",
                        "reason": "Mock parse fallback.",
                        "confidence": 0.0,
                    }
                )
            try:
                payload: Dict[str, Any] = json.loads(m.group(1))
            except json.JSONDecodeError:
                payload = {}
            tir = bool(payload.get("trust_input_labels"))
            idle = payload.get("idle_resources") or {}
            inst = idle.get("instances") if isinstance(idle, dict) else []
            if not isinstance(inst, list):
                inst = []
            return json.dumps(_policy_from_instances(inst, tir))
        return (
            '{"policy_kind": "HOLD", "params": {}, '
            '"justification": "Mock default.", "confidence": 0.8}'
        )

    return strategy
