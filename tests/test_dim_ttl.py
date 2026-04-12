"""Tests for DIM TTL / Decision Validity Window (DIR §6.4)."""

from datetime import datetime, timedelta, timezone

from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal


def _make_proposal(**kwargs) -> PolicyProposal:
    defaults = {
        "dfid": "test-dfid-1",
        "agent_id": "agent_a",
        "policy_kind": "TRADE",
    }
    defaults.update(kwargs)
    return PolicyProposal(**defaults)


def test_ttl_no_valid_until_pass_through() -> None:
    """When valid_until is None and no validity_window_sec, TTL not enforced."""
    proposal = _make_proposal()
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == "ACCEPT"
    assert reason == "Validation passed"


def test_ttl_expired_valid_until() -> None:
    """When valid_until is in the past, reject with TTL_EXPIRED."""
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    proposal = _make_proposal(valid_until=past)
    verdict, reason = validate_proposal(proposal, {}, now=datetime.now(timezone.utc))
    assert verdict == "REJECT"
    assert reason == "TTL_EXPIRED"


def test_ttl_valid_valid_until() -> None:
    """When valid_until is in the future, accept."""
    future = datetime.now(timezone.utc) + timedelta(seconds=60)
    proposal = _make_proposal(valid_until=future)
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == "ACCEPT"


def test_ttl_validity_window_sec_expired() -> None:
    """validity_window_sec puts valid_until in past -> reject."""
    old_created = datetime.now(timezone.utc) - timedelta(seconds=100)
    proposal = _make_proposal(
        created_at=old_created,
        execution_constraints={"validity_window_sec": 30},
    )
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == "REJECT"
    assert reason == "TTL_EXPIRED"


def test_ttl_validity_window_sec_valid() -> None:
    """When validity_window_sec puts valid_until in the future, accept."""
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    proposal = _make_proposal(
        created_at=recent,
        execution_constraints={"validity_window_sec": 60},
    )
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == "ACCEPT"


def test_ttl_explicit_now_parameter() -> None:
    """Explicit now parameter used for TTL check."""
    future = datetime.now(timezone.utc) + timedelta(seconds=60)
    proposal = _make_proposal(valid_until=future)
    # now in future - should still accept (valid_until is even further)
    verdict, _ = validate_proposal(proposal, {}, now=datetime.now(timezone.utc))
    assert verdict == "ACCEPT"

    # Pass now after valid_until
    past_valid = future + timedelta(seconds=1)
    verdict2, reason2 = validate_proposal(proposal, {}, now=past_valid)
    assert verdict2 == "REJECT"
    assert reason2 == "TTL_EXPIRED"

