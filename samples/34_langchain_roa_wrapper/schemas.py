"""Domain shapes, YAML helpers, and scenario loader (Sample Guide §3.3, §8)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from shared.contracts.provider import ContractProvider


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


@dataclass
class FinOpsScenario:
    label: str
    idle_resources: Dict[str, Any]
    expected: str
    show_mission_demo: bool = False
    trust_input_labels: bool = False
    notes: str = ""


def load_scenarios(path: Optional[Path] = None) -> List[FinOpsScenario]:
    p = path or Path(__file__).resolve().parent / "scenarios.yaml"
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    rows = raw.get("scenarios") or []
    out: List[FinOpsScenario] = []
    for row in rows:
        ctx = row.get("context") or {}
        idle = ctx.get("idle_resources") or {}
        if not isinstance(idle, dict):
            idle = {}
        out.append(
            FinOpsScenario(
                label=str(row["label"]),
                idle_resources=idle,
                expected=str(row.get("expected", "ACCEPT")).upper(),
                show_mission_demo=bool(ctx.get("show_mission_demo", False)),
                trust_input_labels=bool(ctx.get("trust_input_labels", False)),
                notes=str(row.get("notes", "")),
            )
        )
    return out


def authoritative_instances_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise ``context_store.instances`` for DIM-facing context."""
    raw = (config.get("context_store") or {}).get("instances") or {}
    return {
        "instances": {
            str(iid): {str(k): v for k, v in (meta or {}).items()}
            for iid, meta in raw.items()
        }
    }


def registry_contract_payload(
    config: Dict[str, Any],
    contracts: ContractProvider,
    agent_id: str,
) -> Dict[str, Any]:
    """Merge provider contract with raw YAML extras (e.g. allowed_environments)."""
    rc = contracts.get_contract(agent_id)
    base = rc.model_dump()
    agents = config.get("agents") or []
    row = next((a for a in agents if a.get("agent_id") == agent_id), None)
    if not row:
        merged = dict(base)
    else:
        extra = dict(row.get("contract") or {})
        merged = {**base, **extra}
        merged["agent_id"] = agent_id
        authority = dict(extra.get("authority") or {})
        resource_scope = dict(authority.get("resource_scope") or {})
        if "environments" in resource_scope:
            merged["allowed_environments"] = list(resource_scope["environments"])
        if row.get("mission"):
            merged["mission"] = row["mission"]
    merged.setdefault(
        "min_confidence_threshold",
        float(merged.get("escalate_on_uncertainty", 0.7)),
    )
    return merged
