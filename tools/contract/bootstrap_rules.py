"""Bootstrap Contract validation rules (DIR Governance section 2.2)."""

from __future__ import annotations

from typing import List

from .presets import get_preset
from .schema import CanonicalContract, IRREVERSIBLE_LIMIT_KEYS


class BootstrapValidationError(Exception):
    """Raised when a contract fails Bootstrap rules."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_bootstrap(contract: CanonicalContract, preset: str | None = None) -> None:
    """
    Enforce Bootstrap Contract rule: every irreversible action class must have
    a hard numerical limit before v1.0.0 can be published.

    INTERFACE and MONITOR roles may omit monetary limits when they have no execution authority.
    """
    errors: List[str] = []
    preset_name = preset or "generic"
    preset_def = get_preset(preset_name)

    if not contract.agent_id.strip():
        errors.append("agent_id must not be empty")

    if not contract.owner.strip():
        errors.append("owner must be set (human accountability)")

    if not contract.mission.statement.strip():
        errors.append("mission must not be empty")

    if contract.version != "1.0.0":
        errors.append(
            f"bootstrap contracts must start at version 1.0.0 (got {contract.version})"
        )

    role = contract.role
    limits = contract.authority.numeric_limits()

    if role == "INTERFACE":
        if contract.authority.allowed_policy_types:
            errors.append(
                "INTERFACE agents must not declare allowed_policy_types (zero execution authority)"
            )
        return _raise_if_errors(errors)

    if role == "MONITOR":
        if limits:
            errors.append("MONITOR agents should not declare monetary irreversible limits")
        return _raise_if_errors(errors)

    required_keys = preset_def.required_limit_keys
    if required_keys:
        missing = [key for key in required_keys if key not in limits]
        if missing:
            errors.append(
                f"preset '{preset_name}' requires irreversible limits: {', '.join(missing)}"
            )
    elif not limits:
        errors.append(
            "at least one positive irreversible limit is required "
            f"(one of: {', '.join(IRREVERSIBLE_LIMIT_KEYS)})"
        )

    for key, value in limits.items():
        if value <= 0:
            errors.append(f"irreversible limit '{key}' must be > 0 (got {value})")

    _raise_if_errors(errors)


def _raise_if_errors(errors: List[str]) -> None:
    if errors:
        raise BootstrapValidationError(errors)
