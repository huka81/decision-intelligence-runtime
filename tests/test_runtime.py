"""Tests for DecisionRuntime facade."""

from dir_core import (
    ContractParameterAmendment,
    DecisionRuntime,
    InvariantSpec,
    PolicyProposal,
    RuntimeContractProjection,
    new_dfid,
    project_contract,
)
from dir_core.data_types import AgentRegistryStatus, DimReasonCode, ValidationVerdict
from dir_core.storage import memory_storage


def test_register_agent_handshake() -> None:
    rt = DecisionRuntime(memory_storage())
    hr = rt.register_agent(
        "agent_a",
        {"permissions": {"allowed_policy_types": ["HOLD"]}},
        "1.0.0",
    )
    assert hr.accepted is True
    assert hr.session_token


def test_register_projection_through_runtime_facade() -> None:
    rt = DecisionRuntime(memory_storage())
    hr = rt.register_projection(
        RuntimeContractProjection(
            agent_id="agent_projection",
            allowed_policy_types=["HOLD"],
        ),
        "1.0.0",
    )

    assert hr.accepted is True
    assert rt.registry.get_agent_projection("agent_projection") is not None


def test_evaluate_proposal_accept_records_audit() -> None:
    bundle = memory_storage()
    rt = DecisionRuntime(bundle)
    dfid = new_dfid()
    rt.register_agent(
        "agent_a",
        {
            "permissions": {"allowed_policy_types": ["HOLD"]},
            "safety_rules": {"min_confidence_threshold": 0.1},
        },
        "1.0.0",
    )
    proposal = PolicyProposal(
        dfid=dfid,
        agent_id="agent_a",
        policy_kind="HOLD",
        params={},
        confidence=0.9,
    )
    verdict, reason = rt.evaluate_proposal(proposal, {"note": "x"})
    assert verdict == ValidationVerdict.ACCEPT
    assert reason == DimReasonCode.VALIDATION_PASSED

    events = rt.audit.events_for_dfid(dfid)
    types = [e["event"] for e in events]
    assert "PROPOSAL_ACCEPT" in types


def test_evaluate_proposal_reject_records_audit() -> None:
    rt = DecisionRuntime(memory_storage())
    dfid = new_dfid()
    rt.register_agent(
        "agent_a",
        {"permissions": {"allowed_policy_types": ["HOLD"]}},
        "1.0.0",
    )
    proposal = PolicyProposal(
        dfid=dfid,
        agent_id="agent_a",
        policy_kind="DISALLOWED",
        params={},
        confidence=0.9,
    )
    verdict, _ = rt.evaluate_proposal(proposal, {})
    assert verdict == ValidationVerdict.REJECT

    events = rt.audit.events_for_dfid(dfid)
    assert any(e["event"] == "PROPOSAL_REJECT" for e in events)


def test_evaluate_proposal_record_audit_false() -> None:
    rt = DecisionRuntime(memory_storage())
    dfid = new_dfid()
    rt.register_agent(
        "agent_a",
        {"permissions": {"allowed_policy_types": ["HOLD"]}},
        "1.0.0",
    )
    proposal = PolicyProposal(
        dfid=dfid,
        agent_id="agent_a",
        policy_kind="HOLD",
        params={},
        confidence=0.9,
    )
    rt.evaluate_proposal(proposal, {}, record_audit=False)
    assert rt.audit.events_for_dfid(dfid) == []


def test_restricted_agent_status_blocks_or_escalates() -> None:
    rt = DecisionRuntime(memory_storage())
    rt.register_agent(
        "agent_a",
        {"permissions": {"allowed_policy_types": ["HOLD"]}},
        "1.0.0",
    )
    proposal = PolicyProposal(
        dfid=new_dfid(),
        agent_id="agent_a",
        policy_kind="HOLD",
        params={},
    )

    for status, expected_verdict, expected_reason in (
        (AgentRegistryStatus.SUSPENDED, ValidationVerdict.REJECT, DimReasonCode.AGENT_SUSPENDED),
        (AgentRegistryStatus.RETIRED, ValidationVerdict.REJECT, DimReasonCode.AGENT_RETIRED),
        (AgentRegistryStatus.DEGRADED, ValidationVerdict.REJECT, DimReasonCode.AGENT_DEGRADED),
        (AgentRegistryStatus.ESCALATION_ONLY, ValidationVerdict.ESCALATE, "AGENT_ESCALATION_ONLY"),
    ):
        assert rt.registry.set_agent_status("agent_a", status) is True
        verdict, reason = rt.evaluate_proposal(proposal, {}, record_audit=False)
        assert verdict == expected_verdict
        assert reason == expected_reason

        assert rt.registry.set_agent_status("agent_a", AgentRegistryStatus.ACTIVE) is True


def test_register_projection_round_trip_preserves_invariants() -> None:
    rt = DecisionRuntime(memory_storage())
    projection = project_contract(
        {
            "subject": {"agent_id": "agent_a"},
            "authority": {
                "allowed_policy_types": ["HOLD"],
                "limits": {"max_order_size_usd": {"value": 500, "unit": "USD"}},
            },
        }
    )
    rt.register_projection(projection, "1.0.0")
    stored = rt.registry.get_agent_projection("agent_a")
    assert stored is not None
    assert stored.invariants
    assert any(spec.type == "range" for spec in stored.invariants)


def test_apply_parameter_amendment_within_envelope() -> None:
    rt = DecisionRuntime(memory_storage())
    dfid = new_dfid()
    projection = RuntimeContractProjection(
        agent_id="agent_a",
        allowed_policy_types=["TRADE"],
        invariants=[
            InvariantSpec(
                id="INV_LIMIT",
                type="range",
                field="params.order_value",
                max=1000,
                reason_code="CONTRACT_LIMIT_EXCEEDED",
                runtime_amendable=True,
                min_floor=100,
                max_ceiling=2000,
            )
        ],
    )
    rt.register_projection(projection, "1.0.0")

    result = rt.apply_parameter_amendment(
        ContractParameterAmendment(
            agent_id="agent_a",
            invariant_id="INV_LIMIT",
            patch={"max": 1500},
            actor_id="owner@example.com",
            dfid=dfid,
        )
    )
    assert result.accepted is True

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id="agent_a",
        policy_kind="TRADE",
        params={"order_value": 1200},
    )
    verdict, _ = rt.evaluate_proposal(proposal, {}, record_audit=False)
    assert verdict == ValidationVerdict.ACCEPT

    events = rt.audit.events_for_dfid(dfid)
    assert any(e["event"] == "CONTRACT_PARAMETER_AMENDED" for e in events)


def test_apply_parameter_amendment_rejects_beyond_ceiling() -> None:
    rt = DecisionRuntime(memory_storage())
    projection = RuntimeContractProjection(
        agent_id="agent_a",
        invariants=[
            InvariantSpec(
                id="INV_LIMIT",
                type="range",
                field="params.order_value",
                max=1000,
                runtime_amendable=True,
                max_ceiling=1200,
            )
        ],
    )
    rt.register_projection(projection, "1.0.0")
    result = rt.apply_parameter_amendment(
        ContractParameterAmendment(
            agent_id="agent_a",
            invariant_id="INV_LIMIT",
            patch={"max": 1500},
            actor_id="owner@example.com",
        )
    )
    assert result.accepted is False
    assert result.reason == "PATCH_EXCEEDS_MAX_CEILING"
