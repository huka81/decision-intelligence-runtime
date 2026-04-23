"""ROA user-space agent — Explain, Policy, Self-Check, Proposal (Guide §5)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from dir_core.models import PolicyProposal, ResponsibilityContract
from dir_core.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _explain_prompt(inp: Dict[str, Any]) -> str:
    note = str(inp.get("note", ""))
    keys = (
        "narrative (string), signals (array of strings), "
        "risks (array of strings), opportunities (array of strings)"
    )
    return (
        "[DIR_ROA_EXPLAIN]\n"
        "Summarize the input for a persistence demo (no trading).\n"
        f"Respond with ONLY valid JSON keys: {keys}.\n\n"
        f"Input note: {note}\n"
    )


def _policy_prompt(inp: Dict[str, Any], explain: Dict[str, Any]) -> str:
    exp_txt = json.dumps(explain, ensure_ascii=True)
    note = str(inp.get("note", ""))
    return (
        "[DIR_ROA_POLICY]\n"
        f"Explain stage (structure only): {exp_txt}\n"
        f"Input note: {note}\n"
        "This agent may only emit HOLD for this sample.\n"
        "Respond with ONLY valid JSON:\n"
        '{"policy_kind": "HOLD", "params": {}, '
        '"justification": "<string>", "confidence": <float 0..1>}\n'
    )


def _system(mission: str, stage: str) -> str:
    return (
        f"{mission}\nStage: {stage}. "
        "Follow the response shape in the user message."
    )


def run_roa_cycle(
    llm: LLMClient,
    contract: ResponsibilityContract,
    ctx: Dict[str, Any],
    dfid: str,
    agent_id: str,
) -> Tuple[Optional[PolicyProposal], str, str]:
    """Explain -> Policy -> Self-Check -> Proposal.

    Returns ``(proposal | None, explain_narrative, self_check_reason)``.
    """
    session = ctx.get("session") or {}
    inp = session.get("input") or {}
    mission = contract.mission or "Repository demo agent."

    explain_raw = ""
    try:
        explain_raw = llm.generate(
            _explain_prompt(inp),
            system=_system(mission, "EXPLAIN"),
        )
    except Exception as exc:
        logger.warning("Explain LLM call failed: %s", exc)

    explain_parsed = parse_llm_json(explain_raw) if explain_raw else None
    if explain_parsed is None:
        explain_parsed = {
            "narrative": "(explain parse failed)",
            "signals": [],
            "risks": [],
            "opportunities": [],
        }
    narrative = str(explain_parsed.get("narrative", ""))

    policy_raw = ""
    try:
        policy_raw = llm.generate(
            _policy_prompt(inp, explain_parsed),
            system=_system(mission, "POLICY"),
        )
    except Exception as exc:
        logger.warning("Policy LLM call failed: %s", exc)

    parsed = parse_llm_json(policy_raw) if policy_raw else None
    if parsed is None:
        proposal = PolicyProposal(
            dfid=dfid,
            agent_id=agent_id,
            policy_kind="HOLD",
            params={},
            justification=(
                "LLM response could not be parsed; defaulting to HOLD."
            ),
            confidence=0.0,
            explain_ref=narrative[:512],
        )
        allowed = list(contract.allowed_policy_types or [])
        if proposal.policy_kind not in allowed:
            msg = "parse failed; HOLD not allowed by contract"
            return None, narrative, msg
        if proposal.confidence < float(contract.escalate_on_uncertainty):
            return (
                None,
                narrative,
                "parse failed; confidence below escalate_on_uncertainty",
            )
        return proposal, narrative, ""

    policy_kind = str(parsed.get("policy_kind", "HOLD"))
    confidence = float(parsed.get("confidence", 0.0))
    justification = str(parsed.get("justification", ""))
    params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}

    allowed = list(contract.allowed_policy_types or [])
    if policy_kind not in allowed:
        msg = (
            f"policy_kind {policy_kind!r} not in "
            f"allowed_policy_types {allowed!r}"
        )
        return None, narrative, msg
    if confidence < float(contract.escalate_on_uncertainty):
        return (
            None,
            narrative,
            f"confidence {confidence} below escalate_on_uncertainty "
            f"{contract.escalate_on_uncertainty}",
        )

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=agent_id,
        policy_kind=policy_kind,
        params=params,
        justification=justification,
        confidence=confidence,
        explain_ref=narrative[:512],
    )
    return proposal, narrative, ""
