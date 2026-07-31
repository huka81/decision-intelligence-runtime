"""LLM-driven contract interview: prompt, parse, merge, validate."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from dir_core.utils.llm_client import LLMClient

from .bootstrap_rules import BootstrapValidationError, validate_bootstrap
from .presets import get_preset
from .render import render_registry_yaml
from .schema import CanonicalContract, IRREVERSIBLE_LIMIT_KEYS, normalize_contract_dict

logger = logging.getLogger(__name__)


class LLMContractResponse(BaseModel):
    """Structured JSON expected from the LLM."""

    assistant_reply: str
    contract_patch: Dict[str, Any] = Field(default_factory=dict)
    change_summary: str = ""


def empty_draft_contract(preset: Optional[str] = None) -> Dict[str, Any]:
    """Minimal draft contract before the user provides details."""
    preset_def = get_preset(preset or "generic")
    return {
        "agent_id": "draft_agent",
        "version": "1.0.0",
        "owner": "",
        "role": preset_def.default_role,
        "mission": "",
        "authority": {
            "authorized_instruments": list(preset_def.authorized_instruments),
            "allowed_policy_types": list(preset_def.allowed_policy_types),
        },
        "responsibility": {
            "explainability": "required",
            "evidence_level": preset_def.evidence_level,
            "escalation": "mandatory",
            "escalate_on_uncertainty": preset_def.escalate_on_uncertainty,
            "aggregate_thresholds": {},
        },
    }


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge patch into base (patch wins on conflicts)."""
    result = dict(base)
    for key, value in patch.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_system_prompt(preset: Optional[str] = None) -> str:
    preset_def = get_preset(preset or "generic")
    required = preset_def.required_limit_keys
    required_text = ", ".join(required) if required else "at least one irreversible limit"
    return f"""You are the Contract Studio assistant for ROA Responsibility Contracts.

Your job: help the user draft a Bootstrap Responsibility Contract (version 1.0.0) through conversation.

Rules:
- Bootstrap rule: every irreversible action must have a hard numerical limit ({required_text}).
- Canonical schema uses nested authority and responsibility blocks.
- Irreversible limits MUST be flat numeric fields under authority, using EXACT keys only:
  {", ".join(IRREVERSIBLE_LIMIT_KEYS)}
  Example: authority.max_discount_pct: 15.0  (NOT irreversible_limits, NOT max_discount_percentage)
- Do NOT nest limits under authority.irreversible_limits.
- owner must be a human accountability email.
- role is one of: STRATEGIST, EXECUTOR, MONITOR, INTERFACE.
- Do not invent irreversible limits without user input; ask when missing.

Domain preset hint: {preset_def.name} — {preset_def.description}
Suggested policy types: {", ".join(preset_def.allowed_policy_types) or "none"}
Suggested limits: {json.dumps(preset_def.suggested_limits)}

Respond with ONLY valid JSON (no markdown fences) matching this schema:
{{
  "assistant_reply": "natural language reply to the user",
  "contract_patch": {{ partial nested contract fields to merge }},
  "change_summary": "short note of what changed"
}}

contract_patch may include top-level fields (agent_id, owner, mission, role, version)
and nested authority/responsibility keys. Only include fields you are setting or updating.
"""


def build_user_prompt(
    current_contract: Dict[str, Any],
    chat_history: List[Tuple[str, str]],
    user_message: str,
) -> str:
    history_lines = []
    for role, content in chat_history[-12:]:
        history_lines.append(f"{role.upper()}: {content}")
    history_text = "\n".join(history_lines) if history_lines else "(no prior messages)"
    return f"""Current contract JSON:
{json.dumps(current_contract, indent=2)}

Conversation so far:
{history_text}

USER: {user_message}

Return JSON with assistant_reply, contract_patch, and change_summary."""


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def parse_llm_response(raw: str) -> LLMContractResponse:
    data = _extract_json(raw)
    return LLMContractResponse.model_validate(data)


def validate_contract_soft(
    contract_dict: Dict[str, Any],
    preset: Optional[str] = None,
) -> Tuple[Optional[CanonicalContract], bool, List[str]]:
    """
    Validate contract; return (model or None, bootstrap_ok, errors).
    Schema errors are listed; bootstrap failures are soft during drafting.
    """
    errors: List[str] = []
    normalized = normalize_contract_dict(contract_dict)
    try:
        contract = CanonicalContract.model_validate(normalized)
    except Exception as exc:
        errors.append(f"schema: {exc}")
        return None, False, errors

    try:
        validate_bootstrap(contract, preset=preset)
        return contract, True, []
    except BootstrapValidationError as exc:
        return contract, False, list(exc.errors)


def process_chat_turn(
    llm: LLMClient,
    *,
    current_contract: Dict[str, Any],
    chat_history: List[Tuple[str, str]],
    user_message: str,
    preset: Optional[str] = None,
) -> Tuple[str, Dict[str, Any], str, bool, List[str], str]:
    """
    Run one LLM turn.

    Returns:
        assistant_reply, merged_contract_dict, contract_yaml,
        validation_ok, validation_errors, change_summary
    """
    system = build_system_prompt(preset)
    prompt = build_user_prompt(current_contract, chat_history, user_message)

    raw = llm.generate(prompt, system=system)
    last_error: Optional[Exception] = None
    parsed: Optional[LLMContractResponse] = None
    for attempt in range(2):
        try:
            parsed = parse_llm_response(raw)
            break
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                retry_prompt = (
                    f"{prompt}\n\n"
                    "Your previous response was not valid JSON. "
                    "Reply with ONLY a JSON object, no markdown."
                )
                raw = llm.generate(retry_prompt, system=system)
    if parsed is None:
        raise ValueError(f"LLM returned invalid JSON: {last_error}") from last_error

    merged = normalize_contract_dict(deep_merge(current_contract, parsed.contract_patch))
    contract, validation_ok, errors = validate_contract_soft(merged, preset=preset)

    if contract is not None:
        yaml_text = render_registry_yaml(contract)
        merged = contract.model_dump(exclude_none=True)
    else:
        yaml_text = "# Contract incomplete — fix validation errors\n" + "\n".join(
            f"# - {e}" for e in errors
        )

    return (
        parsed.assistant_reply,
        merged,
        yaml_text,
        validation_ok,
        errors,
        parsed.change_summary,
    )


def mock_contract_llm_strategy(prompt: str, system: Optional[str] = None) -> str:
    """Deterministic mock for USE_MOCK_LLM demos and tests."""
    lower = prompt.lower()
    patch: Dict[str, Any] = {}
    if "trading" in lower or "crypto" in lower or "buy" in lower:
        patch = {
            "agent_id": "trading_bot_01",
            "owner": "jane.doe@example.com",
            "mission": "Execute crypto market orders safely within capital limits.",
            "role": "EXECUTOR",
            "authority": {
                "authorized_instruments": ["ETH-USD", "BTC-USD"],
                "allowed_policy_types": ["BUY", "SELL", "HOLD"],
                "max_order_size_usd": 50000.0,
                "max_drawdown_limit_pct": 4.0,
            },
        }
    elif "fraud" in lower:
        patch = {
            "agent_id": "fraud_guard_v1",
            "owner": "security@example.com",
            "mission": "Evaluate payment transactions and recommend ALLOW, BLOCK, or CHALLENGE.",
            "authority": {
                "allowed_policy_types": ["ALLOW", "BLOCK", "CHALLENGE"],
                "max_transaction_usd": 5000.0,
            },
        }
    elif "refund" in lower:
        patch = {
            "agent_id": "refund_agent_01",
            "owner": "support@example.com",
            "mission": "Issue refunds only within policy limits.",
            "authority": {
                "allowed_policy_types": ["REFUND", "DENY", "ESCALATE"],
                "max_refund_usd": 50.0,
                "max_discount_pct": 15.0,
            },
        }
    else:
        patch = {
            "agent_id": "my_agent_01",
            "owner": "owner@example.com",
            "mission": "Perform bounded decisions within explicit limits.",
            "authority": {
                "allowed_policy_types": ["ACTION", "HOLD"],
                "max_order_size_usd": 1000.0,
            },
        }

    return json.dumps(
        {
            "assistant_reply": (
                "I updated the contract draft based on your message. "
                "Review the YAML preview and tell me what to adjust."
            ),
            "contract_patch": patch,
            "change_summary": "Mock LLM applied domain defaults from user message.",
        }
    )
