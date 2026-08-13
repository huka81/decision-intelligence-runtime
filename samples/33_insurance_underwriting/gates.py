"""
Deterministic kernel hard gates (DIR §4.1 — not prompt-based).

Optional keyword injection scan (config). Prohibited territories are checked on
**agent-extracted** stated territories, not raw email substrings, so misleading
broker text is resolved by extraction + contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas import ClientApplication, UnderwritingContract


@dataclass
class GateOutcome:
    ok: bool
    code: str
    message: str
    lifecycle_state: str


def scan_prompt_injection(
    full_text: str, patterns: list[str],
) -> GateOutcome | None:
    if not patterns:
        return None
    low = full_text.lower()
    for p in patterns:
        if p.lower() in low:
            return GateOutcome(
                ok=False,
                code="PROMPT_INJECTION",
                message="Blocked: matched injection pattern (kernel gate).",
                lifecycle_state="ABORTED",
            )
    return None


def check_prohibited_in_stated_territories(
    stated_territories: str,
    prohibited: list[str],
) -> GateOutcome | None:
    """Match config list to agent-extracted territory text (not raw email)."""
    low = stated_territories.lower()
    for t in prohibited:
        if t.lower() in low:
            return GateOutcome(
                ok=False,
                code="PROHIBITED_TERRITORY",
                message=(
                    f"Prohibited jurisdiction in agent-extracted territories ({t}). "
                    "Responsibility contract applies; broker instructions "
                    "cannot override."
                ),
                lifecycle_state="ABORTED",
            )
    return None


def check_authority_ceiling(
    context: ClientApplication,
    contract: UnderwritingContract,
) -> GateOutcome | None:
    if context.requested_tiv_usd is None:
        return None
    max_tiv = contract.max_tiv
    if context.requested_tiv_usd > max_tiv:
        return GateOutcome(
            ok=False,
            code="AUTHORITY_CEILING",
            message=(
                f"Broker-requested TiV {context.requested_tiv_usd:,.0f} exceeds "
                f"delegated max_tiv {max_tiv:,.0f} "
                "- escalated to human."
            ),
            lifecycle_state="ESCALATED",
        )
    return None


def run_pre_agent_gates(
    full_text: str,
    context: ClientApplication,
    contract: UnderwritingContract,
    config: dict[str, Any],
) -> GateOutcome | None:
    """
    Before first LLM: optional keyword injection patterns only.

    Territory and limit are enforced after structured extraction (see
    ``run_post_extraction_gates``).
    """
    ep = config.get("email_processing", {})
    inj = ep.get("injection_patterns") or []
    return scan_prompt_injection(full_text, inj)


def run_post_extraction_gates(
    context: ClientApplication,
    stated_territories: str,
    contract: UnderwritingContract,
    config: dict[str, Any],
) -> GateOutcome | None:
    """
    After extraction: prohibited geography in stated_territories, then authority.

    If both fail, return CONTRACT_VIOLATION (binding blocked).
    """
    ep = config.get("email_processing", {})
    prohibited = ep.get("prohibited_territories", [])

    terr = check_prohibited_in_stated_territories(
        stated_territories, prohibited,
    )
    auth = check_authority_ceiling(context, contract)

    if terr is not None and auth is not None:
        return GateOutcome(
            ok=False,
            code="CONTRACT_VIOLATION",
            message=(
                "Agent extraction recovered factual TiV and territories; "
                "binding blocked by contract - "
                f"{terr.message} | {auth.message}"
            ),
            lifecycle_state="ABORTED",
        )
    if terr is not None:
        return terr
    if auth is not None:
        return auth
    return None
