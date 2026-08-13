"""Compile governance context for LLM prompts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Set

from .loader import load_authoring_rules, load_governance_pack, quote_hash, verify_pack_integrity
from .models import GovernanceAnalysis, GovernanceClause, GovernanceContextPack


def build_governance_context(
    *,
    pack_id: str = "roa-dir-v1",
    preset: Optional[str] = None,
    role: Optional[str] = None,
    action_types: Optional[List[str]] = None,
    max_clauses: int = 24,
) -> Dict[str, Any]:
    """
    Build a deterministic governance context snapshot for a session or chat turn.

    Returns dict with pack metadata, selected clause ids, clause summaries, and hash.
    """
    pack = load_governance_pack(pack_id)
    integrity_errors = verify_pack_integrity(pack)
    if integrity_errors:
        raise ValueError(
            "Governance pack integrity failed: " + "; ".join(integrity_errors)
        )

    selected = _select_clauses(
        pack,
        preset=preset,
        role=role,
        action_types=action_types or [],
        max_clauses=max_clauses,
    )
    clause_summaries = [
        {
            "clause_id": c.clause_id,
            "constraint_class": c.constraint_class,
            "normative_level": c.normative_level,
            "statement": c.statement,
            "source": f"{c.source_document}#{c.source_anchor}",
        }
        for c in selected
    ]
    snapshot_payload = {
        "pack_id": pack.pack_id,
        "pack_version": pack.version,
        "preset": preset,
        "role": role,
        "clause_ids": [c.clause_id for c in selected],
        "clauses": clause_summaries,
    }
    digest = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    snapshot_payload["context_hash"] = digest
    return snapshot_payload


def _select_clauses(
    pack: GovernanceContextPack,
    *,
    preset: Optional[str],
    role: Optional[str],
    action_types: List[str],
    max_clauses: int,
) -> List[GovernanceClause]:
    """Deterministic clause selection: fundamentals first, then preset/role/action tags."""
    fundamentals = [c for c in pack.clauses if c.fundamental]
    optional: List[GovernanceClause] = [c for c in pack.clauses if not c.fundamental]

    def score(clause: GovernanceClause) -> int:
        s = 0
        if preset and preset in clause.presets:
            s += 4
        if role and role in clause.roles:
            s += 3
        if clause.normative_level == "mandatory":
            s += 2
        if clause.constraint_class == "transaction_invariant":
            s += 1
        return s

    optional.sort(key=lambda c: (-score(c), c.clause_id))
    selected: List[GovernanceClause] = list(fundamentals)
    seen: Set[str] = {c.clause_id for c in selected}
    for clause in optional:
        if clause.clause_id in seen:
            continue
        if len(selected) >= max_clauses:
            break
        if preset and clause.presets and preset not in clause.presets:
            continue
        if role and clause.roles and role not in clause.roles:
            continue
        selected.append(clause)
        seen.add(clause.clause_id)
    return selected[:max_clauses]


def compile_authoring_rules_for_prompt() -> str:
    """Render authoring ontology from authoring_rules.yaml for LLM prompts."""
    rules = load_authoring_rules()
    lines = [
        "Contract authoring ontology (sections, constraint layers, hard rules):",
        "",
        "Canonical sections:",
    ]
    for name, section in (rules.get("sections") or {}).items():
        purpose = section.get("purpose", "")
        yaml_path = section.get("yaml_path", name)
        not_for = section.get("not_for", "")
        lines.append(f"- {name} ({yaml_path}): {purpose}")
        if not_for:
            lines.append(f"  NOT for: {not_for}")

    lines.append("")
    lines.append("Constraint layers (do not mix):")
    for layer_name, layer in (rules.get("constraint_layers") or {}).items():
        desc = layer.get("description", "")
        loc = layer.get("contract_location", "")
        enforcement = layer.get("enforcement", "")
        scope = layer.get("scope", "")
        lines.append(
            f"- {layer_name}: {desc} | location={loc} | enforcement={enforcement} | scope={scope}"
        )
        never = layer.get("never_place_in") or []
        if never:
            lines.append(f"  NEVER in: {', '.join(never)}")
        if layer.get("requires_temporal_window"):
            forbidden = layer.get("forbidden_windows") or []
            lines.append(
                f"  Requires temporal window (e.g. 24h, 7d). Forbidden windows: "
                f"{', '.join(forbidden)}"
            )

    schema = rules.get("aggregate_policy_schema") or {}
    if schema:
        lines.append("")
        lines.append("Aggregate policy object (governance.aggregate_policies only):")
        req = ", ".join(schema.get("required_fields") or [])
        lines.append(f"  Required fields: {req}")
        ops = ", ".join(schema.get("operators") or [])
        resp = ", ".join(schema.get("responses") or [])
        lines.append(f"  operator: {ops}; response: {resp}")
        forbidden = schema.get("forbidden_field_names") or []
        if forbidden:
            lines.append(f"  Forbidden field names: {', '.join(forbidden)}")
        non_temp = schema.get("non_temporal_window_forbidden") or []
        if non_temp:
            lines.append(
                f"  Forbidden non-temporal windows (including 1t): {', '.join(non_temp)}"
            )

    hard_rules = rules.get("hard_rules") or []
    if hard_rules:
        lines.append("")
        lines.append("Hard authoring rules:")
        for rule in hard_rules:
            lines.append(f"- {rule}")

    lines.append("")
    lines.append(
        "Transaction invariants: record ONLY in governance_analysis.invariant_candidates "
        "(with predicate + linked_limit_key), NOT in governance.aggregate_policies."
    )
    lines.append(
        "Single-transaction limits: authority.limits only. "
        "Empty governance.aggregate_policies is valid for Bootstrap."
    )
    return "\n".join(lines)


def compile_context_for_prompt(
    context_snapshot: Dict[str, Any],
    *,
    governance_analysis: Optional[GovernanceAnalysis] = None,
    prior_warnings: Optional[List[str]] = None,
) -> str:
    """Render governance context block for system or user prompt."""
    lines = [compile_authoring_rules_for_prompt(), ""]
    lines.append(
        "Governance Context Pack (normative clauses — cite clause_id in source_bindings):",
    )
    for clause in context_snapshot.get("clauses", []):
        level = clause.get("normative_level", "mandatory")
        lines.append(
            f"- [{clause['clause_id']}] ({level}) {clause['statement']} "
            f"(source: {clause.get('source', '')})"
        )

    lines.append("")
    lines.append("Process discipline (Build-Time, untrusted LLM synthesis):")
    lines.append(
        "1. Source binding → 2. Candidate synthesis (untrusted) → "
        "3. Deterministic verification → 4. Human adjudication → publish"
    )
    lines.append(
        "Mission does NOT grant execution authority. Mark ambiguities; do not invent limits."
    )

    if governance_analysis is not None:
        lines.append("")
        lines.append("Current governance analysis JSON:")
        lines.append(json.dumps(governance_analysis.model_dump(), indent=2))

    if prior_warnings:
        lines.append("")
        lines.append("Prior semantic warnings (address or explain):")
        for w in prior_warnings[:12]:
            lines.append(f"- {w}")

    return "\n".join(lines)
