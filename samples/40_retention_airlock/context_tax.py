"""Context Tax simulation: growing prompt payload on DIM retry loops."""

from __future__ import annotations

from typing import List, Sequence, Tuple

# Illustrative input-token budget per retry cycle (full transcript resent each time).
_CONTEXT_TAX_TOKENS: Tuple[int, ...] = (200, 450, 800)


def estimate_context_tokens(retry_attempt: int) -> int:
    """Map 0-based retry attempt to illustrative input-token count."""
    idx = min(max(retry_attempt, 0), len(_CONTEXT_TAX_TOKENS) - 1)
    return _CONTEXT_TAX_TOKENS[idx]


def build_prior_failure_trace(failures: Sequence[str]) -> str:
    """Accumulated DIM rejection trace injected into the next policy prompt."""
    if not failures:
        return ""
    lines: List[str] = []
    for i, reason in enumerate(failures, 1):
        lines.append(f"[attempt {i} DIM_REJECT] {reason}")
    return "\n".join(lines)


def format_context_tax_summary(attempts: Sequence[Tuple[int, int]]) -> str:
    """e.g. retry 1: ~200 tokens | retry 2: ~450 tokens | retry 3: ~800 tokens"""
    parts = [f"retry {n}: ~{tok} tokens" for n, tok in attempts]
    return " | ".join(parts)
