"""Bidirectional Reconstruction: Agent B narrative + compression gap detection."""

from __future__ import annotations

import re
from typing import Iterable, Set

from mocks.agent_b_reconstruct import agent_b_reconstruct

__all__ = [
    "agent_b_reconstruct",
    "compression_gap_too_large",
    "evaluate_bidirectional_reconstruction",
    "keyword_overlap",
    "tokenize",
]

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "for",
        "from",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "we",
        "with",
        "your",
    }
)


def tokenize(text: str) -> Set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def keyword_overlap(original: str, reconstructed: str) -> float:
    a = tokenize(original)
    b = tokenize(reconstructed)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def compression_gap_too_large(
    original: str,
    reconstructed: str,
    *,
    min_overlap: float,
    salient_terms: Iterable[str],
) -> bool:
    overlap = keyword_overlap(original, reconstructed)
    if overlap < min_overlap:
        return True
    orig_tokens = tokenize(original)
    recon_tokens = tokenize(reconstructed)
    for term in salient_terms:
        t = term.lower().strip()
        if t in orig_tokens and t not in recon_tokens:
            return True
    return False


def evaluate_bidirectional_reconstruction(
    original_email: str,
    proposal_dict: dict,
    *,
    min_overlap: float,
    salient_terms: Iterable[str],
) -> tuple[bool, str, float]:
    """Returns (passed, reconstructed_narrative, keyword_overlap_score)."""
    reconstructed = agent_b_reconstruct(proposal_dict)
    overlap = keyword_overlap(original_email, reconstructed)
    failed = compression_gap_too_large(
        original_email,
        reconstructed,
        min_overlap=min_overlap,
        salient_terms=salient_terms,
    )
    return (not failed, reconstructed, overlap)
