"""Shared deterministic validation for Contract Studio and its CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from dir_core import project_contract

from .bootstrap_rules import BootstrapValidationError, validate_bootstrap
from .governance.models import GovernanceAnalysis, GovernanceValidationReport
from .governance.validation import validate_authoring_contract, validate_governance_analysis
from .schema import CanonicalContract


@dataclass(frozen=True)
class ContractValidationResult:
    contract: CanonicalContract | None
    validation_ok: bool
    errors: list[str]
    warnings: list[str]
    governance_report: GovernanceValidationReport | None


def validate_contract(
    contract_dict: dict[str, Any],
    preset: str | None = None,
    *,
    governance_analysis: GovernanceAnalysis | None = None,
    pack_id: str = "roa-dir-v1",
) -> tuple[CanonicalContract | None, bool, list[str], list[str]]:
    """Validate schema, Bootstrap, authoring rules, runtime projection and governance."""
    result = validate_contract_detailed(
        contract_dict,
        preset,
        governance_analysis=governance_analysis,
        pack_id=pack_id,
    )
    return result.contract, result.validation_ok, result.errors, result.warnings


def validate_contract_detailed(
    contract_dict: dict[str, Any],
    preset: str | None = None,
    *,
    governance_analysis: GovernanceAnalysis | None = None,
    pack_id: str = "roa-dir-v1",
) -> ContractValidationResult:
    """Return shared validation outcomes including structured formal checks."""
    try:
        contract = CanonicalContract.from_raw(contract_dict)
    except (ValidationError, ValueError, TypeError) as exc:
        return ContractValidationResult(
            contract=None,
            validation_ok=False,
            errors=[f"schema: {exc}"],
            warnings=[],
            governance_report=None,
        )

    blocking: list[str] = []
    try:
        validate_bootstrap(contract, preset=preset)
    except BootstrapValidationError as exc:
        blocking.extend(exc.errors)

    blocking.extend(validate_authoring_contract(contract))
    data = contract.model_dump(mode="json", exclude_none=True)
    try:
        project_contract(data)
    except (ValidationError, ValueError, TypeError) as exc:
        blocking.append(f"RUNTIME_PROJECTION_INVALID: {exc}")

    report = validate_governance_analysis(
        analysis=governance_analysis,
        contract_dict=data,
        pack_id=pack_id,
        preset=preset,
    )
    blocking.extend(f"{issue.code}: {issue.message}" for issue in report.blocking_errors)
    warnings = [f"{issue.code}: {issue.message}" for issue in report.warnings]
    return ContractValidationResult(
        contract=contract,
        validation_ok=not blocking,
        errors=blocking,
        warnings=warnings,
        governance_report=report,
    )
