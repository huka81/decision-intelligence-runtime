"""Load and verify Governance Context Packs against source documents."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional

import yaml

from .models import GovernanceClause, GovernanceContextPack

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKS_DIR = Path(__file__).parent / "packs"
_AUTHORING_RULES_PATH = Path(__file__).parent / "authoring_rules.yaml"
_SOURCE_DOCS = {
    "ROA_MANIFESTO": _REPO_ROOT / "docs" / "01-roa-manifesto" / "ROA_Manifesto.md",
    "DIR_GOVERNANCE": _REPO_ROOT / "docs" / "04-governance" / "DIR_Governance.md",
}


def normalize_quote(text: str) -> str:
    """Normalize quote text for stable hashing and substring search."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    return text


def quote_hash(text: str) -> str:
    return hashlib.sha256(normalize_quote(text).encode("utf-8")).hexdigest()


def load_governance_pack(pack_id: str = "roa-dir-v1") -> GovernanceContextPack:
    """Load a curated governance pack by id."""
    path = _PACKS_DIR / f"{pack_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Governance pack not found: {path}")
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    pack = GovernanceContextPack.model_validate(data)
    return pack


def verify_pack_integrity(pack: GovernanceContextPack) -> List[str]:
    """
    Verify pack clause quotes exist in source documents.
    Returns list of blocking error messages (empty if ok).
    """
    errors: List[str] = []
    for clause in pack.clauses:
        doc_path = _SOURCE_DOCS.get(clause.source_document)
        if doc_path is None or not doc_path.is_file():
            errors.append(
                f"source document missing for clause {clause.clause_id}: "
                f"{clause.source_document}"
            )
            continue
        doc_text = normalize_quote(doc_path.read_text(encoding="utf-8"))
        normalized_quote = normalize_quote(clause.quote)
        if normalized_quote not in doc_text:
            errors.append(
                f"clause {clause.clause_id}: quote not found in {clause.source_document}"
            )
        expected_hash = quote_hash(clause.quote)
        if clause.quote_hash and clause.quote_hash != expected_hash:
            errors.append(
                f"clause {clause.clause_id}: quote_hash mismatch "
                f"(expected {expected_hash[:12]}…)"
            )
    return errors


def default_pack_id() -> str:
    return "roa-dir-v1"


def load_authoring_rules() -> dict:
    """Load Contract Studio authoring ontology (sections, layers, hard rules)."""
    if not _AUTHORING_RULES_PATH.is_file():
        raise FileNotFoundError(f"Authoring rules not found: {_AUTHORING_RULES_PATH}")
    with open(_AUTHORING_RULES_PATH, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("authoring_rules.yaml must be a YAML mapping")
    return data
