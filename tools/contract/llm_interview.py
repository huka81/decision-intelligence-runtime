"""LLM-driven contract interview: prompt, parse, merge, validate."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from dir_core.utils.llm_client import LLMClient

from .bootstrap_rules import BootstrapValidationError, validate_bootstrap
from .governance.context import compile_context_for_prompt, build_governance_context
from .governance.models import ChatTurnResult, GovernanceAnalysis, LLMContractResponse
from .governance.validation import validate_governance_analysis, validate_authoring_contract
from .presets import get_preset
from .render import render_registry_yaml
from .schema import CanonicalContract, IRREVERSIBLE_LIMIT_KEYS, normalize_contract_dict

logger = logging.getLogger(__name__)


def empty_draft_contract(preset: Optional[str] = None) -> Dict[str, Any]:
    """Minimal draft contract before the user provides details."""
    preset_def = get_preset(preset or "generic")
    return {
        "api_version": "roa.dir/v1",
        "kind": "ResponsibilityContract",
        "metadata": {
            "contract_id": "draft_agent",
            "version": "1.0.0",
            "owner": "",
            "source_refs": [],
        },
        "subject": {"agent_id": "draft_agent", "role": preset_def.default_role},
        "mission": {"statement": ""},
        "authority": {
            "allowed_policy_types": list(preset_def.allowed_policy_types),
            "resource_scope": {
                "instruments": list(preset_def.authorized_instruments)
            },
            "limits": {},
        },
        "execution_conditions": {},
        "responsibility": {
            "explainability": "required",
            "evidence": {"level": preset_def.evidence_level},
            "escalation": {
                "mode": "mandatory",
                "confidence_below": preset_def.escalate_on_uncertainty,
            },
        },
        "governance": {"aggregate_policies": []},
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


def build_system_prompt(
    preset: Optional[str] = None,
    *,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    preset_def = get_preset(preset or "generic")
    required = preset_def.required_limit_keys
    required_text = ", ".join(required) if required else "at least one irreversible limit"

    governance_block = ""
    if context_snapshot:
        governance_block = "\n\n" + compile_context_for_prompt(context_snapshot) + "\n"

    return f"""You are the Contract Studio assistant for ROA Responsibility Contracts.

Your job: help the user draft a Bootstrap Responsibility Contract (version 1.0.0) through conversation.

Rules:
- Bootstrap rule: every irreversible action must have a hard numerical limit ({required_text}).
- Always write the canonical blocks: metadata, subject, mission, authority,
    execution_conditions, responsibility, and governance.
- Irreversible limits MUST be objects under authority.limits, using EXACT keys only:
  {", ".join(IRREVERSIBLE_LIMIT_KEYS)}
    Example: authority.limits.max_discount_pct: {{"value": 15.0, "unit": "percent"}}
- metadata.owner must be a human accountability email.
- subject.role is one of: STRATEGIST, EXECUTOR, MONITOR, INTERFACE.
- mission is an object with a non-empty statement.
- Put instruments under authority.resource_scope.instruments.
- Put escalation mode and confidence under responsibility.escalation only (never aggregate_policies).
- governance.aggregate_policies: post-execution rolling-window rules only (see authoring ontology below).
  Required fields: policy_id, metric, window, operator, threshold, unit, response.
  Forbidden: window 1t / single-transaction; on_breach; INV-* policy_ids; copying authority.limits.
- governance_analysis.invariant_candidates: transaction invariants with predicate + linked_limit_key only.
- Empty governance.aggregate_policies: [] is valid for Bootstrap v1.0.0.
- Do not invent irreversible limits or aggregate thresholds without user input; ask when missing.
- Mission does NOT grant execution authority. Mark ambiguities; do not invent numeric bounds.

Domain preset hint: {preset_def.name} — {preset_def.description}
Suggested policy types: {", ".join(preset_def.allowed_policy_types) or "none"}
Suggested limits: {json.dumps(preset_def.suggested_limits)}
{governance_block}
Respond with ONLY valid JSON (no markdown fences) matching this schema:
{{
  "assistant_reply": "natural language reply to the user",
  "contract_patch": {{ partial nested contract fields to merge }},
  "change_summary": "short note of what changed",
  "governance_analysis": {{
    "goal": {{
      "objective": "business goal",
      "success_criteria": [],
      "non_goals": [],
      "source_bindings": [{{"clause_id": "DIR-BOOTSTRAP-001", "rationale": "..."}}]
    }},
    "action_classes": [
      {{
        "action_type": "BUY",
        "reversibility": "irreversible",
        "rationale": "...",
        "source_bindings": [],
        "linked_limit_key": "max_order_size_usd"
      }}
    ],
    "invariant_candidates": [
      {{
        "invariant_id": "INV-ORDER-SIZE",
        "constraint_class": "transaction_invariant",
        "applies_to_actions": ["BUY"],
        "business_rationale": "...",
        "predicate": {{"op": "le", "variable": "order_value", "value": 50000.0}},
        "enforcement_target": "DIM",
        "source_bindings": [{{"clause_id": "DIR-BOOTSTRAP-001", "rationale": "..."}}],
        "linked_limit_key": "max_order_size_usd"
      }}
    ],
    "assumptions": [],
    "ambiguities": [],
    "open_questions": []
  }}
}}

contract_patch may update canonical nested fields only. governance_analysis is required on every turn.
Return compact minified JSON (no markdown fences). Omit empty assumptions/ambiguities arrays.
Limit invariant_candidates to 6 items per turn unless the user explicitly requests more.
"""


def build_user_prompt(
    current_contract: Dict[str, Any],
    chat_history: List[Tuple[str, str]],
    user_message: str,
    *,
    governance_analysis: Optional[GovernanceAnalysis] = None,
    prior_warnings: Optional[List[str]] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    history_lines = []
    for role, content in chat_history[-12:]:
        history_lines.append(f"{role.upper()}: {content}")
    history_text = "\n".join(history_lines) if history_lines else "(no prior messages)"

    extra = ""
    if context_snapshot and governance_analysis is not None:
        extra = "\n" + compile_context_for_prompt(
            context_snapshot,
            governance_analysis=governance_analysis,
            prior_warnings=prior_warnings,
        )

    return f"""Current contract JSON:
{json.dumps(current_contract, indent=2)}

Conversation so far:
{history_text}
{extra}

USER: {user_message}

Return JSON with assistant_reply, contract_patch, change_summary, and governance_analysis."""


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return _parse_json_object(text)


def _parse_json_object(text: str) -> Dict[str, Any]:
    """Parse LLM JSON; attempt brace repair when the model truncates mid-object."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_exc:
        repaired = _close_truncated_json(text)
        if repaired != text:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise first_exc


def _close_truncated_json(text: str) -> str:
    """
    Close unbalanced brackets/braces after a truncated model response.

    Strips trailing partial key/value fragments that often appear when output
    hits max_output_tokens mid-stream.
    """
    trimmed = text.rstrip()
    trimmed = re.sub(r',\s*"[^"]*"\s*:\s*$', "", trimmed)
    trimmed = re.sub(r',\s*"[^"]*"\s*:\s*"[^"]*$', "", trimmed)
    trimmed = re.sub(r',\s*$', "", trimmed)

    open_braces = trimmed.count("{") - trimmed.count("}")
    open_brackets = trimmed.count("[") - trimmed.count("]")
    if open_braces <= 0 and open_brackets <= 0:
        return trimmed
    return trimmed + ("]" * max(open_brackets, 0)) + ("}" * max(open_braces, 0))


def _json_response_likely_truncated(raw: str, exc: Exception) -> bool:
    text = raw.strip()
    if not text.endswith("}") and not text.endswith("]"):
        return True
    if isinstance(exc, json.JSONDecodeError):
        return "char" in str(exc).lower() or exc.pos is not None and exc.pos > len(text) * 0.85
    return False


def parse_llm_response(raw: str) -> LLMContractResponse:
    data = _extract_json(raw)
    return LLMContractResponse.model_validate(data)


def validate_contract_soft(
    contract_dict: Dict[str, Any],
    preset: Optional[str] = None,
    *,
    governance_analysis: Optional[GovernanceAnalysis] = None,
    pack_id: str = "roa-dir-v1",
) -> Tuple[Optional[CanonicalContract], bool, List[str], List[str]]:
    """
    Validate contract and governance analysis.

    Returns (model or None, validation_ok, blocking_errors, warnings).
    validation_ok is True only when schema + bootstrap + governance blocking pass.
    """
    blocking: List[str] = []
    warnings: List[str] = []

    normalized = normalize_contract_dict(contract_dict)
    contract: Optional[CanonicalContract] = None
    try:
        contract = CanonicalContract.model_validate(normalized)
    except Exception as exc:
        blocking.append(f"schema: {exc}")
        return None, False, blocking, warnings

    bootstrap_ok = True
    try:
        validate_bootstrap(contract, preset=preset)
    except BootstrapValidationError as exc:
        bootstrap_ok = False
        blocking.extend(exc.errors)

    authoring_errors = validate_authoring_contract(contract)
    blocking.extend(authoring_errors)

    gov_report = validate_governance_analysis(
        analysis=governance_analysis,
        contract_dict=contract.model_dump(exclude_none=True),
        pack_id=pack_id,
        preset=preset,
    )
    for issue in gov_report.blocking_errors:
        blocking.append(f"{issue.code}: {issue.message}")
    for issue in gov_report.warnings:
        warnings.append(f"{issue.code}: {issue.message}")

    validation_ok = (
        bootstrap_ok
        and gov_report.blocking_ok
        and not blocking
        and not authoring_errors
    )
    return contract, validation_ok, blocking, warnings


def process_chat_turn(
    llm: LLMClient,
    *,
    current_contract: Dict[str, Any],
    chat_history: List[Tuple[str, str]],
    user_message: str,
    preset: Optional[str] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
    prior_warnings: Optional[List[str]] = None,
    prior_analysis: Optional[GovernanceAnalysis] = None,
) -> ChatTurnResult:
    """Run one governance-aware LLM turn."""
    role = current_contract.get("subject", {}).get("role")
    if context_snapshot is None:
        context_snapshot = build_governance_context(
            preset=preset,
            role=role,
            action_types=current_contract.get("authority", {}).get(
                "allowed_policy_types", []
            ),
        )

    system = build_system_prompt(preset, context_snapshot=context_snapshot)
    prompt = build_user_prompt(
        current_contract,
        chat_history,
        user_message,
        governance_analysis=prior_analysis,
        prior_warnings=prior_warnings,
        context_snapshot=context_snapshot,
    )

    raw = llm.generate(prompt, system=system)
    last_error: Optional[Exception] = None
    parsed: Optional[LLMContractResponse] = None
    for attempt in range(3):
        try:
            parsed = parse_llm_response(raw)
            break
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            truncated = _json_response_likely_truncated(raw, exc)
            if attempt >= 2:
                break
            compact_hint = (
                "Return ONLY compact minified JSON (no markdown). "
                "Limit invariant_candidates to 6 entries. "
                "Omit empty assumptions/ambiguities arrays. "
                "Keep source_bindings to one clause per item."
            )
            if truncated:
                compact_hint = (
                    "Your previous JSON was truncated (output too long). "
                    + compact_hint
                )
            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous response was invalid: {exc}\n"
                f"{compact_hint}\n"
                "Reply with ONLY a JSON object matching LLMContractResponse schema."
            )
            raw = llm.generate(retry_prompt, system=system)
    if parsed is None:
        raise ValueError(f"LLM returned invalid JSON: {last_error}") from last_error

    merged = normalize_contract_dict(deep_merge(current_contract, parsed.contract_patch))
    analysis = parsed.governance_analysis or prior_analysis
    contract, validation_ok, blocking, warnings = validate_contract_soft(
        merged,
        preset=preset,
        governance_analysis=analysis,
    )
    gov_report = validate_governance_analysis(
        analysis=analysis,
        contract_dict=merged,
        preset=preset,
    )

    if contract is not None:
        yaml_text = render_registry_yaml(contract)
        merged = contract.model_dump(exclude_none=True)
    else:
        yaml_text = "# Contract incomplete — fix validation errors\n" + "\n".join(
            f"# - {e}" for e in blocking
        )

    return ChatTurnResult(
        assistant_reply=parsed.assistant_reply,
        merged_contract=merged,
        contract_yaml=yaml_text,
        validation_ok=validation_ok,
        blocking_errors=blocking,
        warnings=warnings,
        change_summary=parsed.change_summary,
        governance_analysis=analysis,
        validation_report=gov_report,
        llm_response=parsed,
    )


def _governance_analysis_for_domain(
    domain: str,
    *,
    actions: List[str],
    limits: Dict[str, Any],
    mission: str,
) -> Dict[str, Any]:
    action_classes = []
    invariant_candidates = []
    for action in actions:
        linked = None
        for key in limits:
            if key in IRREVERSIBLE_LIMIT_KEYS:
                linked = key
                break
        action_classes.append(
            {
                "action_type": action,
                "reversibility": "irreversible" if linked else "reversible",
                "rationale": f"Domain {domain} action.",
                "source_bindings": [{"clause_id": "DIR-BOOTSTRAP-001", "rationale": "Bootstrap limits"}],
                "linked_limit_key": linked,
            }
        )
    for key, spec in limits.items():
        val = spec.get("value", spec) if isinstance(spec, dict) else spec
        invariant_candidates.append(
            {
                "invariant_id": f"INV-{key.upper().replace('_', '-')}",
                "constraint_class": "transaction_invariant",
                "applies_to_actions": actions,
                "business_rationale": f"Hard limit on {key}.",
                "predicate": {"op": "le", "variable": key, "value": float(val)},
                "enforcement_target": "DIM",
                "source_bindings": [{"clause_id": "DIR-BOOTSTRAP-001", "rationale": "Bootstrap rule"}],
                "linked_limit_key": key,
            }
        )

    return {
        "goal": {
            "objective": mission,
            "success_criteria": ["Operate within declared hard limits"],
            "non_goals": ["Expand authority without human review"],
            "source_bindings": [
                {"clause_id": "ROA-MISSION-001", "rationale": "Mission is interpretive only"},
            ],
        },
        "action_classes": action_classes,
        "invariant_candidates": invariant_candidates,
        "assumptions": [],
        "ambiguities": [],
        "open_questions": [],
    }


def mock_contract_llm_strategy(prompt: str, system: Optional[str] = None) -> str:
    """Deterministic mock for USE_MOCK_LLM demos and tests."""
    lower = prompt.lower()
    patch: Dict[str, Any] = {}
    domain = "generic"
    if "trading" in lower or "crypto" in lower or "buy" in lower:
        domain = "trading"
        patch = {
            "metadata": {
                "contract_id": "trading_bot_01",
                "owner": "jane.doe@example.com",
            },
            "subject": {"agent_id": "trading_bot_01", "role": "EXECUTOR"},
            "mission": {
                "statement": "Execute crypto market orders safely within capital limits."
            },
            "authority": {
                "allowed_policy_types": ["BUY", "SELL", "HOLD"],
                "resource_scope": {"instruments": ["ETH-USD", "BTC-USD"]},
                "limits": {
                    "max_order_size_usd": {"value": 50000.0, "unit": "USD"},
                    "max_drawdown_limit_pct": {"value": 4.0, "unit": "percent"},
                },
            },
        }
    elif "fraud" in lower:
        domain = "fraud"
        patch = {
            "metadata": {"contract_id": "fraud_guard_v1", "owner": "security@example.com"},
            "subject": {"agent_id": "fraud_guard_v1", "role": "EXECUTOR"},
            "mission": {
                "statement": "Evaluate payment transactions and recommend ALLOW, BLOCK, or CHALLENGE."
            },
            "authority": {
                "allowed_policy_types": ["ALLOW", "BLOCK", "CHALLENGE"],
                "limits": {
                    "max_transaction_usd": {"value": 5000.0, "unit": "USD"}
                },
            },
        }
    elif "refund" in lower:
        domain = "refund"
        patch = {
            "metadata": {"contract_id": "refund_agent_01", "owner": "support@example.com"},
            "subject": {"agent_id": "refund_agent_01", "role": "EXECUTOR"},
            "mission": {"statement": "Issue refunds only within policy limits."},
            "authority": {
                "allowed_policy_types": ["REFUND", "DENY", "ESCALATE"],
                "limits": {
                    "max_refund_usd": {"value": 50.0, "unit": "USD"},
                    "max_discount_pct": {"value": 15.0, "unit": "percent"},
                },
            },
        }
    else:
        patch = {
            "metadata": {"contract_id": "my_agent_01", "owner": "operator@example.com"},
            "subject": {"agent_id": "my_agent_01", "role": "EXECUTOR"},
            "mission": {"statement": "Perform bounded decisions within explicit limits."},
            "authority": {
                "allowed_policy_types": ["ACTION", "HOLD"],
                "limits": {
                    "max_order_size_usd": {"value": 1000.0, "unit": "USD"}
                },
            },
        }

    mission = patch.get("mission", {}).get("statement", "")
    if isinstance(patch.get("mission"), str):
        mission = patch["mission"]
    authority = patch.get("authority", {})
    limits = authority.get("limits", {})
    actions = authority.get("allowed_policy_types", [])

    return json.dumps(
        {
            "assistant_reply": (
                "I updated the contract draft based on your message. "
                "Review the YAML preview and governance analysis."
            ),
            "contract_patch": patch,
            "change_summary": "Mock LLM applied domain defaults from user message.",
            "governance_analysis": _governance_analysis_for_domain(
                domain, actions=actions, limits=limits, mission=mission
            ),
        }
    )
