"""Tests for Intent Retry Governor (DIR §6.2)."""

from dir.dim import validate_proposal
from dir.intent_retry import REASONING_EXHAUSTION, IntentRetryGovernor
from dir.models import PolicyProposal


def test_record_and_should_abort_memory() -> None:
    """In-memory backend: record rejection, should_abort after max."""
    gov = IntentRetryGovernor(max_retries=3, db_path=None)
    assert gov.should_abort("df1") is False
    assert gov.record_rejection("df1") == 1
    assert gov.record_rejection("df1") == 2
    assert gov.should_abort("df1") is False
    assert gov.record_rejection("df1") == 3
    assert gov.should_abort("df1") is True


def test_reset() -> None:
    """Reset clears count."""
    gov = IntentRetryGovernor(max_retries=3, db_path=None)
    gov.record_rejection("df1")
    gov.record_rejection("df1")
    gov.reset("df1")
    assert gov.should_abort("df1") is False
    assert gov.record_rejection("df1") == 1


def test_dim_integration_reasoning_exhaustion() -> None:
    """DIM returns REASONING_EXHAUSTION when governor says abort."""
    gov = IntentRetryGovernor(max_retries=2, db_path=None)
    context = {"state": {"risk_score": 0.9}}

    # deploy_to_production + risk>0.8 -> REJECT
    def mk() -> PolicyProposal:
        return PolicyProposal(
            dfid="d1", agent_id="a1", policy_kind="deploy_to_production"
        )

    v1, r1 = validate_proposal(mk(), context, retry_governor=gov)
    assert v1 == "REJECT"
    assert "Risk score" in r1

    v2, _ = validate_proposal(mk(), context, retry_governor=gov)
    assert v2 == "REJECT"

    # Third: should_abort -> REASONING_EXHAUSTION
    v3, r3 = validate_proposal(mk(), context, retry_governor=gov)
    assert v3 == "REJECT"
    assert r3 == REASONING_EXHAUSTION


def test_dim_no_governor_no_record() -> None:
    """Without governor, normal validation; no recording."""
    proposal = PolicyProposal(
        dfid="d1", agent_id="a1", policy_kind="deploy_to_production"
    )
    context = {"state": {"risk_score": 0.9}}
    v, r = validate_proposal(proposal, context)
    assert v == "REJECT"
    assert "Risk score" in r
