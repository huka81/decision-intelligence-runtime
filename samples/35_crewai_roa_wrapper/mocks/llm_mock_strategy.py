"""Deterministic JSON for ``setup_environment`` when ``USE_MOCK_LLM=1`` (Sample Guide §12).

The CrewAI path uses ``agent.run_claims_roa_cycle`` with ``use_crew_llm=False`` instead of this client.
This strategy still satisfies bootstrap when the shared ``LLMClient`` is instantiated.
"""

from __future__ import annotations

from typing import Callable, Optional


def make_mock_strategy() -> Callable[[str, Optional[str]], str]:
    def _mock_strategy(prompt: str, system: Optional[str] = None) -> str:
        return (
            '{"policy_kind": "REFUND", "params": {"order_id": "ord_000", "amount_eur": 1.0, '
            '"category": "electronics", "reason": "mock"}, '
            '"justification": "Mock deterministic default.", "confidence": 0.85}'
        )

    return _mock_strategy
