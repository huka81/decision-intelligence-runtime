"""Semantic Alignment Check — proxy gaming detector (User Space, DIM-adjacent)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from schemas import SemanticAlignmentConfig


@dataclass
class AlignmentResult:
    passed: bool
    flag: Optional[str]
    reason: str
    aborted: bool = False


def check_semantic_alignment(
    justification: str,
    config: SemanticAlignmentConfig,
    *,
    strict_blocking: Optional[bool] = None,
) -> AlignmentResult:
    """
    Deterministic proxy-gaming detector.

    Production systems may use a lightweight LLM here (DIR-minified §4.4).
    """
    text = justification.lower()
    strict = config.strict_blocking if strict_blocking is None else strict_blocking

    gaming_hits = [p for p in config.proxy_gaming_phrases if p in text]
    mission_hits = [k for k in config.mission_rationale_keywords if k in text]

    if gaming_hits and len(mission_hits) < 2:
        reason = (
            f"SEMANTIC_MISMATCH: proxy gaming phrases detected "
            f"({', '.join(gaming_hits)}) without sufficient mission rationale"
        )
        if strict:
            return AlignmentResult(
                passed=False,
                flag="SEMANTIC_MISMATCH",
                reason=reason,
                aborted=True,
            )
        return AlignmentResult(
            passed=True,
            flag="NEEDS_REVIEW",
            reason=reason,
            aborted=False,
        )

    return AlignmentResult(passed=True, flag=None, reason="OK", aborted=False)
