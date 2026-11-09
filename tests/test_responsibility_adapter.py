from __future__ import annotations

import pytest

from dir_core import (
    ContractRole,
    RuntimeContractProjection,
    project_contract,
    responsibility_contract_from_projection,
)


def _canonical(**overrides):
    contract = {
        "api_version": "roa.dir/v1",
        "kind": "ResponsibilityContract",
        "metadata": {"version": "1.0.0"},
        "subject": {
            "agent_id": "pos_01",
            "role": "EXECUTOR",
            "parent_agent_id": "strategist_01",
        },
        "mission": {"statement": "Hold safely."},
        "authority": {
            "allowed_policy_types": ["HOLD", "CLOSE"],
            "resource_scope": {"instruments": ["ETH-USD"]},
            "limits": {"max_order_size_usd": {"value": 1000, "unit": "USD"}},
        },
        "execution_conditions": {"wake_up_threshold_pct": 0.25},
        "responsibility": {"escalation": {"mode": "mandatory", "confidence_below": 0.6}},
    }
    contract.update(overrides)
    return contract


def test_projection_keeps_parent_agent_id() -> None:
    projection = project_contract(_canonical())
    assert isinstance(projection, RuntimeContractProjection)
    assert projection.parent_agent_id == "strategist_01"


def test_adapter_maps_canonical_projection_to_flat_contract() -> None:
    rc = responsibility_contract_from_projection(project_contract(_canonical()))
    assert rc.agent_id == "pos_01"
    assert rc.role == ContractRole.EXECUTOR
    assert rc.mission == "Hold safely."
    assert rc.authorized_instruments == ["ETH-USD"]
    assert rc.allowed_policy_types == ["HOLD", "CLOSE"]
    assert rc.escalate_on_uncertainty == 0.6
    assert rc.wake_up_threshold_pct == 0.25
    assert rc.parent_agent_id == "strategist_01"


def test_adapter_uses_defaults_when_optional_blocks_missing() -> None:
    contract = _canonical(execution_conditions={}, responsibility={})
    rc = responsibility_contract_from_projection(project_contract(contract))
    assert rc.escalate_on_uncertainty == 0.7
    assert rc.wake_up_threshold_pct == 0.5
    assert rc.max_drawdown_limit == 0.05


def test_adapter_drawdown_fraction_and_percent() -> None:
    fraction = _canonical()
    fraction["authority"]["limits"]["max_drawdown_limit"] = {"value": 0.04, "unit": "fraction"}
    assert responsibility_contract_from_projection(project_contract(fraction)).max_drawdown_limit == 0.04

    percent = _canonical()
    percent["authority"]["limits"]["max_drawdown_limit_pct"] = {"value": 4.0, "unit": "percent"}
    assert responsibility_contract_from_projection(project_contract(percent)).max_drawdown_limit == pytest.approx(0.04)
