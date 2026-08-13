"""Tests for DecisionRuntime facade."""

from dir_core import DecisionRuntime, PolicyProposal, RuntimeContractProjection, new_dfid
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
