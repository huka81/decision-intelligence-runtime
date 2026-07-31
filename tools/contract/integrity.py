"""Formal YAML parse + integrity checks for Contract Studio."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .bootstrap_rules import BootstrapValidationError, validate_bootstrap
from .schema import CanonicalContract


def strip_yaml_comments(text: str) -> str:
    """Remove full-line comments (keeps inline content; evolve-later blocks stay out)."""
    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_contract_yaml(yaml_text: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Parse YAML text into a dict. Returns (data, parse_errors)."""
    errors: List[str] = []
    cleaned = strip_yaml_comments(yaml_text).strip()
    if not cleaned:
        return None, ["YAML is empty after removing comments"]
    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError as exc:
        return None, [f"YAML parse error: {exc}"]
    if data is None:
        return None, ["YAML parsed to null"]
    if not isinstance(data, dict):
        return None, [f"YAML root must be a mapping, got {type(data).__name__}"]
    return data, errors


def contract_content_hash(contract_dict: Dict[str, Any]) -> str:
    """Stable SHA-256 of canonical contract JSON (sorted keys)."""
    payload = json.dumps(contract_dict, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_contract_yaml(
    yaml_text: str,
    *,
    preset: Optional[str] = None,
    expected_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Formally parse YAML and confirm integrity.

    Checks:
    1. YAML syntax (safe_load)
    2. CanonicalContract schema (Pydantic)
    3. Bootstrap irreversible-limit rules
    4. Optional round-trip vs stored contract_json (content hash)
    """
    checks: Dict[str, Any] = {
        "yaml_parse": {"ok": False, "detail": ""},
        "schema": {"ok": False, "detail": ""},
        "bootstrap": {"ok": False, "detail": ""},
        "content_hash": {"ok": None, "detail": "", "sha256": None},
    }
    errors: List[str] = []

    data, parse_errors = parse_contract_yaml(yaml_text)
    if parse_errors or data is None:
        checks["yaml_parse"] = {"ok": False, "detail": "; ".join(parse_errors)}
        errors.extend(parse_errors)
        return {
            "integrity_ok": False,
            "checks": checks,
            "errors": errors,
            "contract": None,
            "sha256": None,
        }

    checks["yaml_parse"] = {"ok": True, "detail": "YAML parsed successfully"}

    try:
        contract = CanonicalContract.from_raw(data)
        checks["schema"] = {
            "ok": True,
            "detail": f"CanonicalContract valid for agent_id={contract.agent_id}",
        }
    except Exception as exc:
        checks["schema"] = {"ok": False, "detail": str(exc)}
        errors.append(f"schema: {exc}")
        return {
            "integrity_ok": False,
            "checks": checks,
            "errors": errors,
            "contract": data,
            "sha256": None,
        }

    dumped = contract.model_dump(exclude_none=True)
    digest = contract_content_hash(dumped)
    checks["content_hash"]["sha256"] = digest

    try:
        validate_bootstrap(contract, preset=preset)
        checks["bootstrap"] = {"ok": True, "detail": "Bootstrap rules passed"}
    except BootstrapValidationError as exc:
        checks["bootstrap"] = {"ok": False, "detail": "; ".join(exc.errors)}
        errors.extend(exc.errors)

    if expected_json is not None:
        try:
            expected_contract = CanonicalContract.from_raw(expected_json)
            expected_hash = contract_content_hash(
                expected_contract.model_dump(exclude_none=True)
            )
            match = expected_hash == digest
            checks["content_hash"]["ok"] = match
            checks["content_hash"]["detail"] = (
                "YAML matches stored revision hash"
                if match
                else f"YAML hash {digest[:12]}… differs from revision {expected_hash[:12]}…"
            )
            if not match:
                errors.append("content_hash mismatch vs stored contract_json")
        except Exception as exc:
            checks["content_hash"]["ok"] = False
            checks["content_hash"]["detail"] = f"Could not hash stored revision: {exc}"
            errors.append(str(exc))
    else:
        checks["content_hash"]["ok"] = True
        checks["content_hash"]["detail"] = "SHA-256 computed (no revision comparison)"

    integrity_ok = (
        checks["yaml_parse"]["ok"]
        and checks["schema"]["ok"]
        and checks["bootstrap"]["ok"]
        and checks["content_hash"]["ok"] is not False
    )

    return {
        "integrity_ok": integrity_ok,
        "checks": checks,
        "errors": errors,
        "contract": {
            "agent_id": contract.agent_id,
            "version": contract.version,
            "owner": contract.owner,
            "role": contract.role,
        },
        "sha256": digest,
    }
