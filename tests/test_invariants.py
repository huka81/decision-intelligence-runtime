"""Tests for declarative invariant evaluators."""

from dir_core import PolicyProposal, RuntimeContractProjection
from dir_core.data_types import DimReasonCode
from dir_core.invariants import (
    evaluate_invariants,
    evaluate_range_rule,
    evaluate_set_rule,
    evaluate_state_match_rule,
)
from dir_core.models import InvariantSpec


def _proposal(**kwargs) -> PolicyProposal:
    defaults = {
        "dfid": "dfid-1",
        "agent_id": "agent_a",
        "policy_kind": "TRADE",
    }
    defaults.update(kwargs)
    return PolicyProposal(**defaults)


def test_range_rule_accepts_within_bounds() -> None:
    rule = InvariantSpec(
        id="INV_LIMIT",
        type="range",
        field="params.order_value",
        max=1000,
        reason_code="CONTRACT_LIMIT_EXCEEDED",
    )
    assert evaluate_range_rule(rule, _proposal(params={"order_value": 500})) is None


def test_range_rule_rejects_above_max() -> None:
    rule = InvariantSpec(
        id="INV_LIMIT",
        type="range",
        field="params.order_value",
        max=1000,
        reason_code="CONTRACT_LIMIT_EXCEEDED",
    )
    failure = evaluate_range_rule(rule, _proposal(params={"order_value": 1001}))
    assert failure is not None
    assert failure.invariant_id == "INV_LIMIT"
    assert failure.reason == "CONTRACT_LIMIT_EXCEEDED"


def test_set_rule_rejects_unknown_policy() -> None:
    rule = InvariantSpec(
        id="INV_ALLOWED",
        type="set",
        field="policy_kind",
        allowed=["HOLD"],
        reason_code="UNAUTHORIZED_POLICY_TYPE",
    )
    failure = evaluate_set_rule(rule, _proposal(policy_kind="TRADE"))
    assert failure is not None
    assert failure.reason == "UNAUTHORIZED_POLICY_TYPE"


def test_set_rule_rejects_denied_value_case_insensitively() -> None:
    rule = InvariantSpec(
        id="INV_INDUSTRY",
        type="set",
        field="params.industry",
        denied=["Fireworks", "CryptoMining"],
        reason_code="PROHIBITED_INDUSTRY",
    )
    failure = evaluate_set_rule(
        rule,
        _proposal(params={"industry": "fireworks"}),
    )
    assert failure is not None
    assert failure.reason == "PROHIBITED_INDUSTRY"


def test_set_rule_rejects_denied_substring() -> None:
    rule = InvariantSpec(
        id="INV_TERRITORY",
        type="set",
        field="params.stated_territories",
        denied=["syria", "damascus"],
        match="substring",
        reason_code="PROHIBITED_TERRITORY",
    )
    failure = evaluate_set_rule(
        rule,
        _proposal(params={"stated_territories": "Stock held in Damascus, Syria"}),
    )
    assert failure is not None
    assert failure.reason == "PROHIBITED_TERRITORY"


def test_evaluate_invariants_only_applies_to_matching_policy_kind() -> None:
    projection = RuntimeContractProjection(
        agent_id="agent_a",
        invariants=[
            InvariantSpec(
                id="INV_INTAKE_LIMIT",
                type="range",
                field="params.requested_tiv_usd",
                max=100,
                applies_to_policy_kinds=["INTAKE_AUTHORITY_SCREEN"],
            )
        ],
    )
    assert (
        evaluate_invariants(
            _proposal(policy_kind="BIND", params={}),
            projection,
            {},
        )
        == []
    )
    failures = evaluate_invariants(
        _proposal(
            policy_kind="INTAKE_AUTHORITY_SCREEN",
            params={"requested_tiv_usd": 101},
        ),
        projection,
        {},
    )
    assert len(failures) == 1
    assert failures[0].invariant_id == "INV_INTAKE_LIMIT"


def test_state_match_rule_rejects_drift() -> None:
    rule = InvariantSpec(
        id="INV_PRICE",
        type="state_match",
        field="params.reference_price",
        snapshot_path="state.price",
        drift_envelope_pct=0.5,
        reason_code="STALE_PRICE_CONTEXT",
    )
    failure = evaluate_state_match_rule(
        rule,
        _proposal(params={"reference_price": 102}),
        {"state": {"price": 100}},
    )
    assert failure is not None
    assert failure.reason == "STALE_PRICE_CONTEXT"


def test_evaluate_invariants_on_projection() -> None:
    projection = RuntimeContractProjection(
        agent_id="agent_a",
        allowed_policy_types=["TRADE"],
        invariants=[
            InvariantSpec(
                id="INV_LIMIT",
                type="range",
                field="params.order_value",
                max=100,
                reason_code="CONTRACT_LIMIT_EXCEEDED",
            )
        ],
    )
    failures = evaluate_invariants(
        _proposal(params={"order_value": 150}),
        projection,
        {},
    )
    assert len(failures) == 1
    assert failures[0].reason == DimReasonCode.CONTRACT_LIMIT_EXCEEDED or failures[0].reason == "CONTRACT_LIMIT_EXCEEDED"


def test_evaluate_invariants_collects_all_failures() -> None:
    projection = RuntimeContractProjection(
        agent_id="agent_a",
        invariants=[
            InvariantSpec(
                id="INV_TERRITORY",
                type="set",
                field="params.territory",
                denied=["syria"],
                match="substring",
                reason_code="PROHIBITED_TERRITORY",
            ),
            InvariantSpec(
                id="INV_MAX_TIV",
                type="range",
                field="params.total_insured_value",
                max=3_000_000,
                reason_code="AUTHORITY_CEILING",
            ),
        ],
    )
    failures = evaluate_invariants(
        _proposal(
            policy_kind="BIND",
            params={"territory": "Syria", "total_insured_value": 5_000_000},
        ),
        projection,
        {},
    )
    assert [failure.invariant_id for failure in failures] == [
        "INV_TERRITORY",
        "INV_MAX_TIV",
    ]
    assert [failure.reason for failure in failures] == [
        "PROHIBITED_TERRITORY",
        "AUTHORITY_CEILING",
    ]
