"""Tests for contract validation, compilation and canonical rendering."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from dir_core import RuntimeContractProjection, project_contract
from samples.shared.contracts.provider import YamlContractProvider
from tools.contract.bootstrap_rules import validate_bootstrap
from tools.contract.cli import main
from tools.contract.render import render_registry_yaml, render_sample_fragment
from tools.contract.schema import CanonicalContract
from tools.contract.validation import validate_contract


@pytest.fixture
def contract_path(tmp_path: Path) -> Path:
    contract = CanonicalContract(
        agent_id="payments_01",
        owner="payments.owner@example.org",
        mission="Issue bounded refunds.",
        authority={
            "allowed_policy_types": ["REFUND"],
            "limits": {"max_refund_usd": {"value": 50.0, "unit": "USD"}},
            "invariants": [
                {
                    "id": "INV_COUNTRY",
                    "type": "set",
                    "field": "state.property.country",
                    "denied": ["KP", "IR", "SY"],
                }
            ],
        },
    )
    path = tmp_path / "contract.yaml"
    path.write_text(render_registry_yaml(contract), encoding="utf-8")
    return path


def test_cli_validate(contract_path: Path, capsys) -> None:
    assert main(["validate", str(contract_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("OK:")
    assert "ANALYSIS_MISSING" in captured.err


def test_cli_compile_stdout_is_projection_json(contract_path: Path, capsys) -> None:
    assert main(["compile", str(contract_path)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    projection = RuntimeContractProjection.model_validate(result)
    expected = project_contract(
        CanonicalContract.from_raw(yaml.safe_load(contract_path.read_text(encoding="utf-8")))
        .model_dump(mode="json", exclude_none=True)
    )
    assert projection == expected
    assert projection.release.contract_id == "payments_01"
    assert projection.release.contract_version == "1.0.0"
    assert any(spec.field == "state.property.country" for spec in projection.invariants)
    assert any(spec.max == 50 for spec in projection.invariants)
    assert "ANALYSIS_MISSING" in captured.err
    assert main(["compile", str(contract_path)]) == 0
    assert capsys.readouterr().out == captured.out


def test_cli_compile_file(contract_path: Path, tmp_path: Path, capsys) -> None:
    output = tmp_path / "projection.json"
    assert main(["compile", str(contract_path), "--out", str(output)]) == 0
    assert capsys.readouterr().out == ""
    projection = RuntimeContractProjection.model_validate_json(output.read_text(encoding="utf-8"))
    assert projection.agent_id == "payments_01"


@pytest.mark.parametrize("command", ["validate", "compile"])
@pytest.mark.parametrize("content", ["", "- item", "authority: {{{", "null", "42"])
def test_cli_invalid_yaml(command: str, content: str, tmp_path: Path, capsys) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(content, encoding="utf-8")
    assert main([command, str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "failed" in captured.err.lower()


@pytest.mark.parametrize("command", ["validate", "compile"])
def test_cli_missing_file(command: str, tmp_path: Path, capsys) -> None:
    assert main([command, str(tmp_path / "missing.yaml")]) == 1
    assert capsys.readouterr().err


def test_cli_invalid_contract_does_not_overwrite_output(contract_path: Path, tmp_path: Path, capsys) -> None:
    contract_path.write_text(
        contract_path.read_text(encoding="utf-8").replace("payments.owner@example.org", "owner@example.com"),
        encoding="utf-8",
    )
    output = tmp_path / "projection.json"
    output.write_text("unchanged", encoding="utf-8")
    assert main(["compile", str(contract_path), "--out", str(output)]) == 1
    assert output.read_text(encoding="utf-8") == "unchanged"
    assert "PLACEHOLDER_IDENTITY" in capsys.readouterr().err


def test_cli_compile_reports_write_failure(contract_path: Path, tmp_path: Path, capsys) -> None:
    assert main(["compile", str(contract_path), "--out", str(tmp_path)]) == 1
    assert "compile failed" in capsys.readouterr().err


def test_cli_preset_validation(contract_path: Path, capsys) -> None:
    assert main(["validate", str(contract_path), "--preset", "trading"]) == 1
    assert "max_order_size_usd" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["init", "from-sample"])
def test_cli_authoring_commands_removed(command: str, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main([command])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_shared_validation_rejects_runtime_incompatible_role(contract_path: Path) -> None:
    data = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    data["subject"]["role"] = "INTERFACE"
    data["authority"] = {}
    contract, ok, errors, _ = validate_contract(data)
    assert contract is not None
    assert not ok
    assert any("RUNTIME_PROJECTION_INVALID" in error for error in errors)
    assert data["subject"]["role"] == "INTERFACE"


@pytest.mark.parametrize("command", ["validate", "compile"])
def test_cli_rejects_runtime_incompatible_scope(command: str, contract_path: Path, capsys) -> None:
    data = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    data["authority"]["resource_scope"] = {"match": {"substring": ["home"]}}
    contract_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main([command, str(contract_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "RUNTIME_PROJECTION_INVALID" in captured.err


def test_shared_validation_rejects_invalid_invariant(contract_path: Path) -> None:
    data = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    data["authority"]["invariants"][0]["allowed"] = ["US"]
    _, ok, errors, _ = validate_contract(data)
    assert not ok
    assert any("INVARIANT_SET_MODE" in error for error in errors)


def test_integrity_revalidates_governance_analysis(contract_path: Path) -> None:
    from tools.contract.governance.models import GoalModel, GovernanceAnalysis, SourceBinding
    from tools.contract.integrity import verify_contract_yaml

    analysis = GovernanceAnalysis(
        goal=GoalModel(
            objective="Issue bounded refunds",
            source_bindings=[SourceBinding(clause_id="UNKNOWN_CLAUSE")],
        )
    )
    result = verify_contract_yaml(
        contract_path.read_text(encoding="utf-8"), governance_analysis=analysis
    )
    assert not result["integrity_ok"]
    assert any("INVALID_CLAUSE_REF" in error for error in result["errors"])


def test_canonical_contract_and_validate() -> None:
    contract = CanonicalContract(
        agent_id="fraud_guard_v1",
        owner="fraud.owner@example.org",
        role="EXECUTOR",
        mission="Evaluate transactions.",
        authority={
            "allowed_policy_types": ["ALLOW", "BLOCK"],
            "limits": {"max_transaction_usd": {"value": 5000.0, "unit": "USD"}},
        },
    )
    validate_bootstrap(contract, preset="fraud_gate")
    limit = contract.authority.limits["max_transaction_usd"]
    assert limit.value == 5000.0
    assert limit.unit == "USD"
    assert contract.subject.agent_id == "fraud_guard_v1"
    assert contract.metadata.owner == "fraud.owner@example.org"


def test_renderers_emit_only_canonical_contract_shape() -> None:
    contract = CanonicalContract(
        agent_id="bot_01",
        owner="owner@example.com",
        mission="Trade safely.",
        authority={
            "allowed_policy_types": ["BUY"],
            "limits": {"max_order_size_usd": {"value": 1000.0, "unit": "USD"}},
        },
    )

    for rendered in (render_registry_yaml(contract), render_sample_fragment(contract)):
        data = yaml.safe_load(rendered)
        assert list(data) == [
            "api_version",
            "kind",
            "metadata",
            "subject",
            "mission",
            "authority",
            "execution_conditions",
            "responsibility",
            "governance",
        ]
        assert data["api_version"] == "roa.dir/v1"
        assert data["kind"] == "ResponsibilityContract"
        assert data["mission"] == {"statement": "Trade safely."}
        assert data["authority"]["limits"]["max_order_size_usd"] == {
            "value": 1000.0,
            "unit": "USD",
        }
        assert not {"agent_id", "version", "owner", "role"} & data.keys()


def test_aggregate_policy_valid_temporal_window() -> None:
    base = {
        "agent_id": "bot_01",
        "owner": "o@example.com",
        "mission": "Trade safely.",
        "authority": {"max_order_size_usd": 1000.0},
    }
    policy = {
        "policy_id": "daily_drawdown",
        "metric": "rolling_drawdown_pct",
        "window": "24h",
        "operator": "gt",
        "threshold": 4.0,
        "unit": "percent",
        "response": "SUSPENDED",
    }
    contract = CanonicalContract.model_validate(
        {**base, "governance": {"aggregate_policies": [policy]}}
    )
    assert len(contract.governance.aggregate_policies) == 1
    assert contract.governance.aggregate_policies[0].window == "24h"


def test_aggregate_policy_rejects_single_transaction_window() -> None:
    base = {
        "agent_id": "bot_01",
        "owner": "o@example.com",
        "mission": "Trade safely.",
        "authority": {"max_transaction_usd": 2500.0},
    }
    bad = {
        "policy_id": "max_tx",
        "metric": "transaction_value_usd",
        "window": "1t",
        "operator": "le",
        "threshold": 2500.0,
        "unit": "USD",
        "response": "SUSPENDED",
    }
    try:
        CanonicalContract.model_validate(
            {**base, "governance": {"aggregate_policies": [bad]}}
        )
        assert False, "expected validation error"
    except Exception:
        pass


def test_aggregate_policy_maps_legacy_on_breach() -> None:
    base = {
        "agent_id": "bot_01",
        "owner": "o@example.com",
        "mission": "Trade safely.",
        "authority": {"max_order_size_usd": 1000.0},
    }
    legacy = {
        "policy_id": "rolling_volume",
        "metric": "bound_volume_usd",
        "window": "7d",
        "operator": "gt",
        "threshold": 10000.0,
        "unit": "USD",
        "on_breach": "SUSPEND",
    }
    contract = CanonicalContract.model_validate(
        {**base, "governance": {"aggregate_policies": [legacy]}}
    )
    pol = contract.governance.aggregate_policies[0]
    assert pol.response == "SUSPENDED"


def test_validate_authoring_rejects_placeholder_and_dup_limit() -> None:
    from tools.contract.governance.validation import validate_authoring_contract

    contract = CanonicalContract.model_validate(
        {
            "agent_id": "draft_agent",
            "owner": "owner@example.com",
            "mission": "Negotiate policies.",
            "authority": {
                "limits": {
                    "max_transaction_usd": {"value": 2500.0, "unit": "USD"},
                },
            },
            "governance": {
                "aggregate_policies": [
                    {
                        "policy_id": "INV-TX",
                        "metric": "transaction_value_usd",
                        "window": "24h",
                        "operator": "le",
                        "threshold": 2500.0,
                        "unit": "USD",
                        "response": "SUSPENDED",
                    }
                ],
            },
        }
    )
    errors = validate_authoring_contract(contract)
    assert any("PLACEHOLDER_IDENTITY" in e for e in errors)
    assert any("INVARIANT_LEAKED_TO_AGGREGATE" in e for e in errors)
    assert any("AGGREGATE_DUP_LIMIT" in e for e in errors)


def test_project_contract_canonical_shape() -> None:
    projection = project_contract(
        {
            "api_version": "roa.dir/v1",
            "metadata": {
                "contract_id": "bot",
                "version": "1.2.0",
                "contract_hash": "abc",
            },
            "subject": {"agent_id": "bot-1", "role": "EXECUTOR"},
            "mission": {"statement": "Trade safely."},
            "authority": {
                "allowed_policy_types": ["BUY"],
                "limits": {"max_order_size": {"value": 1000, "unit": "USD"}},
            },
        }
    )

    assert isinstance(projection, RuntimeContractProjection)
    assert projection.release.contract_hash == "abc"
    assert projection.transaction_limits["max_order_size"]["value"] == 1000


def test_project_contract_legacy_shape() -> None:
    projection = project_contract(
        {
            "agent_id": "legacy",
            "role": "EXECUTOR",
            "permissions": {
                "allowed_policy_types": ["HOLD"],
                "max_order_size_usd": 500,
            },
        }
    )

    assert projection.agent_id == "legacy"
    assert projection.allowed_policy_types == ["HOLD"]
    assert projection.transaction_limits["max_order_size_usd"]["value"] == 500
    assert any(spec.type == "range" for spec in projection.invariants)


def test_compile_authority_invariants_from_canonical_limits() -> None:
    from tools.contract.invariants import compile_authority_invariants

    compiled = compile_authority_invariants(
        {
            "authority": {
                "allowed_policy_types": ["BUY"],
                "limits": {"max_order_size": {"value": 1000, "unit": "USD"}},
            }
        }
    )
    assert any(spec.id == "INV_ALLOWED_POLICY_TYPES" for spec in compiled)
    assert any(spec.type == "range" and spec.max == 1000 for spec in compiled)


def test_compile_authority_exclusion_to_denied_set() -> None:
    from tools.contract.invariants import compile_authority_invariants

    compiled = compile_authority_invariants(
        {
            "authority": {
                "exclusions": {
                    "prohibited_industries": ["Fireworks", "CryptoMining"]
                }
            }
        }
    )
    exclusion = next(
        spec for spec in compiled if spec.id == "INV_PROHIBITED_INDUSTRIES"
    )
    assert exclusion.field == "params.industry"
    assert exclusion.denied == ["Fireworks", "CryptoMining"]


def test_invariant_ir_rejects_mixed_set_modes() -> None:
    from tools.contract.governance.validation import validate_contract_invariant_ir

    errors = validate_contract_invariant_ir(
        {
            "authority": {
                "invariants": [
                    {
                        "id": "INV_SET",
                        "type": "set",
                        "field": "params.kind",
                        "allowed": ["A"],
                        "denied": ["B"],
                    }
                ]
            }
        }
    )
    assert any("INVARIANT_SET_MODE" in error for error in errors)


def test_explicit_invariant_conflict_detected() -> None:
    from tools.contract.governance.validation import validate_authority_invariant_conflicts

    errors = validate_authority_invariant_conflicts(
        {
            "authority": {
                "allowed_policy_types": ["BUY"],
                "invariants": [
                    {
                        "id": "INV_ALLOWED_POLICY_TYPES",
                        "type": "set",
                        "field": "policy_kind",
                        "allowed": ["BUY"],
                    }
                ],
            }
        }
    )
    assert errors


def test_normalize_preserves_explicit_currency_limit() -> None:
    contract = CanonicalContract.from_raw(
        {
            "metadata": {
                "contract_id": "refund_agent",
                "version": "1.0.0",
                "owner": "owner@example.com",
            },
            "subject": {"agent_id": "refund_agent", "role": "EXECUTOR"},
            "mission": {"statement": "Issue bounded refunds."},
            "authority": {
                "allowed_policy_types": ["REFUND"],
                "limits": {
                    "max_refund_eur": {"value": 50.0, "unit": "EUR"}
                },
            },
        }
    )
    assert "max_refund_usd" not in contract.authority.limits
    assert contract.authority.limits["max_refund_eur"].unit == "EUR"


def test_yaml_contract_provider_loads_canonical_envelope() -> None:
    nested = {
        "agents": [
            {
                "agent_id": "canonical_agent",
                "contract": {
                    "api_version": "roa.dir/v1",
                    "kind": "ResponsibilityContract",
                    "metadata": {
                        "version": "1.0.0",
                        "owner": "owner@example.com",
                    },
                    "subject": {"agent_id": "canonical_agent", "role": "EXECUTOR"},
                    "mission": {"statement": "Hold safely."},
                    "authority": {
                        "allowed_policy_types": ["HOLD"],
                        "limits": {
                            "max_transaction_usd": {"value": 1000, "unit": "USD"}
                        },
                    },
                    "responsibility": {
                        "explainability": "required",
                        "escalation": {"mode": "mandatory", "confidence_below": 0.6},
                    },
                },
            }
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        yaml.safe_dump(nested, handle)
        path = handle.name

    try:
        provider = YamlContractProvider(path)
        contract = provider.get_contract("canonical_agent")
        assert contract.mission == "Hold safely."
        assert contract.allowed_policy_types == ["HOLD"]
        assert contract.escalate_on_uncertainty == 0.6
    finally:
        Path(path).unlink(missing_ok=True)
