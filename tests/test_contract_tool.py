"""Tests for tools/contract Bootstrap wizard."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from dir_core import ResponsibilityContract, RuntimeContractProjection, project_contract
from tools.contract.bootstrap_rules import validate_bootstrap
from tools.contract.flatten import flatten_canonical, flatten_contract_dict
from tools.contract.from_sample import answers_from_sample
from tools.contract.render import render_registry_yaml, render_sample_fragment
from tools.contract.schema import CanonicalContract, InterviewAnswers
from samples.shared.contracts.provider import YamlContractProvider


def test_interview_answers_to_canonical_and_validate() -> None:
    answers = InterviewAnswers(
        preset="fraud_gate",
        agent_id="fraud_guard_v1",
        owner="owner@example.com",
        role="EXECUTOR",
        mission="Evaluate transactions.",
        allowed_policy_types=["ALLOW", "BLOCK"],
        irreversible_limits={"max_transaction_usd": 5000.0},
    )
    contract = answers.to_canonical()
    validate_bootstrap(contract, preset="fraud_gate")
    limit = contract.authority.limits["max_transaction_usd"]
    assert limit.value == 5000.0
    assert limit.unit == "USD"
    assert contract.subject.agent_id == "fraud_guard_v1"
    assert contract.metadata.owner == "owner@example.com"


def test_renderers_emit_only_canonical_contract_shape() -> None:
    contract = InterviewAnswers(
        agent_id="bot_01",
        owner="owner@example.com",
        mission="Trade safely.",
        allowed_policy_types=["BUY"],
        irreversible_limits={"max_order_size_usd": 1000.0},
    ).to_canonical()

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


def test_flatten_round_trip_dir_core() -> None:
    contract = CanonicalContract(
        agent_id="bot_01",
        owner="o@example.com",
        mission="Trade safely.",
        authority={
            "authorized_instruments": ["ETH-USD"],
            "allowed_policy_types": ["BUY"],
            "max_order_size_usd": 1000.0,
            "max_drawdown_limit_pct": 4.0,
        },
    )
    flat = flatten_canonical(contract)
    rc = ResponsibilityContract(**flat)
    assert rc.agent_id == "bot_01"
    assert rc.max_drawdown_limit == 0.04
    assert flat["permissions"]["max_order_size_usd"] == 1000.0


def test_flatten_contract_dict_nested() -> None:
    nested = {
        "agent_id": "a1",
        "role": "EXECUTOR",
        "mission": "m",
        "authority": {
            "allowed_policy_types": ["HOLD"],
            "max_order_size_usd": 500.0,
        },
        "responsibility": {"escalate_on_uncertainty": 0.8},
    }
    flat = flatten_contract_dict(nested)
    assert flat["allowed_policy_types"] == ["HOLD"]
    assert flat["permissions"]["max_order_size_usd"] == 500.0


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


def test_from_sample_quick_start() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    answers = answers_from_sample(repo_root / "samples" / "00_quick_start")
    assert answers.agent_id == "trading_bot_01"
    assert "max_order_size_usd" in answers.irreversible_limits
    assert "max_drawdown_limit_pct" in answers.irreversible_limits
    contract = answers.to_canonical()
    validate_bootstrap(contract, preset=answers.preset)


def test_from_sample_preserves_canonical_limit_unit() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    answers = answers_from_sample(
        repo_root / "samples" / "33_insurance_underwriting"
    )
    contract = answers.to_canonical()
    assert contract.authority.limits["max_tiv"].value == 3000000.0
    assert contract.authority.limits["max_tiv"].unit == "USD"


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


def test_yaml_contract_provider_flattens_nested() -> None:
    from samples.shared.contracts.provider import YamlContractProvider

    nested = {
        "agents": [
            {
                "agent_id": "nested_agent",
                "contract": {
                    "role": "EXECUTOR",
                    "mission": "Test nested load.",
                    "authority": {
                        "allowed_policy_types": ["ACTION"],
                        "max_transaction_usd": 100.0,
                    },
                    "responsibility": {"escalate_on_uncertainty": 0.6},
                },
            }
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        yaml.dump(nested, handle)
        path = handle.name

    try:
        provider = YamlContractProvider(path)
        contract = provider.get_contract("nested_agent")
        assert contract.agent_id == "nested_agent"
        assert contract.allowed_policy_types == ["ACTION"]
    finally:
        Path(path).unlink(missing_ok=True)


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
