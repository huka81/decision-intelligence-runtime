"""Kernel Space validators: Syntactic contract + Fact + Evidence + Bidirectional governance."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from dir_core import PolicyProposal

from evidence import classify_customer_intent, is_retention_action
from reconstruction import agent_b_reconstruct, compression_gap_too_large


def fact_tier_limit(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    _contract: Dict[str, Any],
) -> Optional[str]:
    """Differential heuristic: proposed discount vs tier limit from ground-truth store."""
    if proposal.policy_kind != "APPLY_DISCOUNT":
        return None
    try:
        proposed = float(proposal.params.get("discount_pct", 0.0))
    except (TypeError, ValueError):
        return "FACT_VALIDATION: invalid discount_pct"
    max_allowed = float(context.get("max_discount_pct", 15.0))
    if proposed > max_allowed + 1e-9:
        return (
            f"FACT_VIOLATION: proposed {proposed:.2f}% exceeds tier limit {max_allowed:.2f}%"
        )
    return None


def evidence_conflict(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    _contract: Dict[str, Any],
) -> Optional[str]:
    """Evidence-based validation: independent intent signal vs proposed action."""
    email_body = str(context.get("email_body", ""))
    patterns = list(context.get("cancel_intent_patterns") or [])
    retention_actions = list(context.get("retention_actions") or ["APPLY_DISCOUNT"])
    intent = classify_customer_intent(email_body, patterns)
    if intent == "CANCEL_SUBSCRIPTION" and is_retention_action(
        proposal.policy_kind, retention_actions
    ):
        return (
            "EVIDENTIAL_CONFLICT: independent classifier detected CANCEL_SUBSCRIPTION "
            f"but proposal is {proposal.policy_kind}"
        )
    return None


def bidirectional_reconstruction(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    _contract: Dict[str, Any],
) -> Optional[str]:
    """Bidirectional Reconstruction: can the output explain itself against the original context?"""
    if not context.get("enable_bidirectional_reconstruction"):
        return None
    if proposal.policy_kind != "APPLY_DISCOUNT":
        return None
    original_email = str(context.get("email_body", ""))
    reconstructed = agent_b_reconstruct(proposal.model_dump(mode="json"))
    min_overlap = float(context.get("bidirectional_min_overlap", 0.25))
    salient = list(context.get("bidirectional_salient_terms") or [])
    if compression_gap_too_large(
        original_email,
        reconstructed,
        min_overlap=min_overlap,
        salient_terms=salient,
    ):
        return "COMPRESSION_DRIFT: output cannot explain its own context"
    return None


def dim_validators() -> List[
    Callable[[PolicyProposal, Dict[str, Any], Dict[str, Any]], Optional[str]]
]:
    return [fact_tier_limit, evidence_conflict, bidirectional_reconstruction]


def build_dim_context(
    *,
    customer_id: str,
    customer_tier: str,
    email_body: str,
    max_discount_pct: float,
    cancel_intent_patterns: List[str],
    retention_actions: List[str],
    dfid: str,
    agent_id: str,
    enable_bidirectional_reconstruction: bool = False,
    bidirectional_min_overlap: float = 0.25,
    bidirectional_salient_terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "customer_id": customer_id,
        "customer_tier": customer_tier,
        "email_body": email_body,
        "max_discount_pct": max_discount_pct,
        "cancel_intent_patterns": cancel_intent_patterns,
        "retention_actions": retention_actions,
        "enable_bidirectional_reconstruction": enable_bidirectional_reconstruction,
        "bidirectional_min_overlap": bidirectional_min_overlap,
        "bidirectional_salient_terms": bidirectional_salient_terms or [],
        "meta": {"dfid": dfid, "agent_id": agent_id},
        "state": {"risk_score": 0.1},
    }


def gate_trace_from_reason(reason: str) -> Dict[str, str]:
    """Map DIM reason to airlock layer outcomes for reporting."""
    reason_s = str(reason)
    syntax = "PASS"
    fact = "PASS"
    evidence = "PASS"
    bidirectional = "PASS"

    if "not in allowed_policy_types" in reason_s or "Missing policy_kind" in reason_s:
        syntax = "REJECT"
    elif "REASONING_EXHAUSTION" in reason_s:
        syntax = "REJECT"
        fact = "REJECT"
    elif "FACT_VIOLATION" in reason_s:
        fact = "REJECT"
    elif "EVIDENTIAL_CONFLICT" in reason_s:
        evidence = "REJECT"
    elif "COMPRESSION_DRIFT" in reason_s:
        bidirectional = "REJECT"

    return {
        "syntactic": syntax,
        "fact_validation": fact,
        "evidence_validation": evidence,
        "bidirectional_reconstruction": bidirectional,
    }
