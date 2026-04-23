"""Domain shapes, scenario loader, and DIM handshake payload (Sample Guide §3.3, §8)."""

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
class ClaimsScenario:
    label: str
    expected: str
    claim: Optional[Dict[str, Any]] = None
    claim_text: Optional[str] = None
    notes: str = ""


def load_scenarios(path: Optional[Path] = None) -> List[ClaimsScenario]:
    p = path or Path(__file__).resolve().parent / "scenarios.yaml"
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    rows = raw.get("scenarios") or []
    out: List[ClaimsScenario] = []
    for row in rows:
        ctx = row.get("context") or {}
        claim = ctx.get("claim")
        claim_text = ctx.get("claim_text")
        if claim is not None and not isinstance(claim, dict):
            claim = None
        if claim_text is not None:
            claim_text = str(claim_text).strip() or None
        if claim is None and not claim_text:
            raise ValueError(f"Scenario '{row.get('label')}' needs context.claim or context.claim_text")
        out.append(
            ClaimsScenario(
                label=str(row["label"]),
                expected=str(row.get("expected", "ACCEPT")).upper(),
                claim=dict(claim) if claim else None,
                claim_text=claim_text,
                notes=str(row.get("notes", "")),
            )
        )
    return out


def orders_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    raw = (config.get("context_store") or {}).get("orders") or {}
    return {
        str(oid): {str(k): v for k, v in (meta or {}).items()}
        for oid, meta in raw.items()
    }


def registry_claims_contract_payload(
    config: Dict[str, Any],
    contracts: ContractProvider,
    agent_id: str,
) -> Dict[str, Any]:
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
        if row.get("mission"):
            merged["mission"] = row["mission"]
    merged.setdefault(
        "min_confidence_threshold",
        float(merged.get("escalate_on_uncertainty", 0.7)),
    )
    return merged


@dataclass
class CrewConfig:
    analyst_role: str
    analyst_goal: str
    decision_maker_role: str
    decision_maker_goal: str

    @classmethod
    def from_dict(cls, crew_cfg: Dict[str, Any]) -> "CrewConfig":
        return cls(
            analyst_role=str(crew_cfg.get("analyst_role", "Claims Analyst")),
            analyst_goal=str(
                crew_cfg.get(
                    "analyst_goal",
                    "Analyze a customer refund claim and summarize eligibility.",
                )
            ),
            decision_maker_role=str(crew_cfg.get("decision_maker_role", "Decision Maker")),
            decision_maker_goal=str(
                crew_cfg.get(
                    "decision_maker_goal",
                    "Based on analyst findings, produce a refund proposal as JSON. "
                    "Use action=REFUND always. The DIR Kernel enforces all limits.",
                )
            ),
        )
