"""Canonical dir-core invariant integration tests for sample 33."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_DIR = _REPO_ROOT / "samples" / "33_insurance_underwriting"
for _path in (
    _REPO_ROOT,
    _REPO_ROOT / "src",
    _REPO_ROOT / "samples",
    _SAMPLE_DIR,
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from dir_core.agent_registry import AgentRegistry
from dir_core.contract_projection import project_contract
from dir_core.data_types import ValidationVerdict
from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal as RuntimePolicyProposal
from dir_core.storage import memory_storage
from shared.config import load_yaml_config


@pytest.fixture
def sample_contract() -> dict:
    config = load_yaml_config(_SAMPLE_DIR / "config.yaml")
    return dict(config["agents"][0]["contract"])


@pytest.fixture
def registry(sample_contract: dict) -> AgentRegistry:
    result = AgentRegistry(storage=memory_storage().agent_registry)
    handshake = result.handshake(
        "underwriter_agent",
        sample_contract,
        "1.0.0",
    )
    assert handshake.accepted, handshake.reason
    return result


def _runtime_proposal(territory: str, tiv: float) -> RuntimePolicyProposal:
    return RuntimePolicyProposal(
        dfid="dfid-test",
        agent_id="underwriter_agent",
        policy_kind="BIND",
        params={
            "total_insured_value": tiv,
            "territory": territory,
        },
        justification="test",
    )


def test_sample_contract_is_pure_invariant_ir(sample_contract: dict) -> None:
    authority = sample_contract["authority"]
    assert "limits" not in authority
    assert "exclusions" not in authority
    assert "execution_conditions" not in sample_contract

    projection = project_contract(sample_contract)
    ids = {spec.id for spec in projection.invariants}
    assert ids == {
        "INV_ALLOWED_POLICY_TYPES",
        "INV_TERRITORY",
        "INV_MAX_TIV",
    }


def test_validate_proposal_accepts_within_contract(registry: AgentRegistry) -> None:
    projection = registry.get_agent_projection("underwriter_agent")
    verdict, reason = validate_proposal(
        _runtime_proposal("United Kingdom", 1_500_000),
        {},
        contract=projection,
    )
    assert verdict == ValidationVerdict.ACCEPT
    assert reason == "VALIDATION_PASSED"


def test_validate_proposal_rejects_prohibited_territory(registry: AgentRegistry) -> None:
    projection = registry.get_agent_projection("underwriter_agent")
    verdict, reason = validate_proposal(
        _runtime_proposal("Damascus, Syrian Arab Republic", 1_000_000),
        {},
        contract=projection,
    )
    assert verdict == ValidationVerdict.REJECT
    assert reason == "PROHIBITED_TERRITORY"


def test_validate_proposal_rejects_authority_ceiling(registry: AgentRegistry) -> None:
    projection = registry.get_agent_projection("underwriter_agent")
    verdict, reason = validate_proposal(
        _runtime_proposal("United Kingdom", 4_000_000),
        {},
        contract=projection,
    )
    assert verdict == ValidationVerdict.REJECT
    assert reason == "AUTHORITY_CEILING"


def test_validate_proposal_reports_all_failures(registry: AgentRegistry) -> None:
    projection = registry.get_agent_projection("underwriter_agent")
    context: dict = {}
    verdict, reason = validate_proposal(
        _runtime_proposal("Operations in Syria and Damascus", 5_000_000),
        context,
        contract=projection,
    )
    assert verdict == ValidationVerdict.REJECT
    assert reason == "PROHIBITED_TERRITORY;AUTHORITY_CEILING"
    failures = context["_dim_audit"]["failures"]
    assert [item["invariant_id"] for item in failures] == [
        "INV_TERRITORY",
        "INV_MAX_TIV",
    ]
    assert [item["reason"] for item in failures] == [
        "PROHIBITED_TERRITORY",
        "AUTHORITY_CEILING",
    ]
