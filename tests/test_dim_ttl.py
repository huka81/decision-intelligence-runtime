"""Tests for DIM TTL / Decision Validity Window (DIR §6.4)."""

from datetime import datetime, timedelta, timezone

from dir_core.data_types import DimReasonCode, ValidationVerdict
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
    assert verdict == ValidationVerdict.ACCEPT
    assert reason == DimReasonCode.VALIDATION_PASSED


def test_ttl_expired_valid_until() -> None:
    """When valid_until is in the past, reject with TTL_EXPIRED."""
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    proposal = _make_proposal(valid_until=past)
    verdict, reason = validate_proposal(proposal, {}, now=datetime.now(timezone.utc))
    assert verdict == ValidationVerdict.REJECT
    assert reason == DimReasonCode.TTL_EXPIRED


def test_ttl_valid_valid_until() -> None:
    """When valid_until is in the future, accept."""
    future = datetime.now(timezone.utc) + timedelta(seconds=60)
    proposal = _make_proposal(valid_until=future)
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == ValidationVerdict.ACCEPT


def test_ttl_validity_window_sec_expired() -> None:
    """validity_window_sec puts valid_until in past -> reject."""
    old_created = datetime.now(timezone.utc) - timedelta(seconds=100)
    proposal = _make_proposal(
        created_at=old_created,
        execution_constraints={"validity_window_sec": 30},
    )
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == ValidationVerdict.REJECT
    assert reason == DimReasonCode.TTL_EXPIRED


def test_ttl_validity_window_sec_valid() -> None:
    """When validity_window_sec puts valid_until in the future, accept."""
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    proposal = _make_proposal(
        created_at=recent,
        execution_constraints={"validity_window_sec": 60},
    )
    verdict, reason = validate_proposal(proposal, {})
    assert verdict == ValidationVerdict.ACCEPT


def test_ttl_explicit_now_parameter() -> None:
    """Explicit now parameter used for TTL check."""
    future = datetime.now(timezone.utc) + timedelta(seconds=60)
    proposal = _make_proposal(valid_until=future)
    # now in future - should still accept (valid_until is even further)
    verdict, _ = validate_proposal(proposal, {}, now=datetime.now(timezone.utc))
    assert verdict == ValidationVerdict.ACCEPT

    # Pass now after valid_until
    past_valid = future + timedelta(seconds=1)
    verdict2, reason2 = validate_proposal(proposal, {}, now=past_valid)
    assert verdict2 == ValidationVerdict.REJECT
    assert reason2 == DimReasonCode.TTL_EXPIRED


def test_dim_contract_allowed_policy_types_accept() -> None:
    """When policy_kind is in allowed_policy_types, accept."""
    contract = {"permissions": {"allowed_policy_types": ["TRADE", "HOLD"]}}
    proposal = _make_proposal(policy_kind="TRADE")
    verdict, _ = validate_proposal(proposal, {}, contract=contract)
    assert verdict == ValidationVerdict.ACCEPT


def test_dim_contract_allowed_policy_types_reject() -> None:
    """When policy_kind is not in allowed_policy_types, reject."""
    contract = {"permissions": {"allowed_policy_types": ["HOLD"]}}
    proposal = _make_proposal(policy_kind="TRADE")
    verdict, reason = validate_proposal(proposal, {}, contract=contract)
    assert verdict == ValidationVerdict.REJECT
    assert "not in allowed_policy_types" in reason


def test_dim_contract_min_confidence_accept() -> None:
    """When confidence is >= min_confidence_threshold, accept."""
    contract = {"safety_rules": {"min_confidence_threshold": 0.8}}
    proposal = _make_proposal(confidence=0.85)
    verdict, _ = validate_proposal(proposal, {}, contract=contract)
    assert verdict == ValidationVerdict.ACCEPT


def test_dim_contract_min_confidence_reject() -> None:
    """When confidence is < min_confidence_threshold, reject."""
    contract = {"safety_rules": {"min_confidence_threshold": 0.8}}
    proposal = _make_proposal(confidence=0.7)
    verdict, reason = validate_proposal(proposal, {}, contract=contract)
    assert verdict == ValidationVerdict.REJECT
    assert "below threshold" in reason


def test_dim_custom_validator_accept() -> None:
    """When custom validator returns None, accept."""
    def custom_val(prop, ctx, cont):
        return None
    
    proposal = _make_proposal()
    verdict, _ = validate_proposal(proposal, {}, custom_validators=[custom_val])
    assert verdict == ValidationVerdict.ACCEPT


def test_dim_custom_validator_reject() -> None:
    """When custom validator returns string, reject with that string."""
    def custom_val(prop, ctx, cont):
        return "custom error reason"
    
    proposal = _make_proposal()
    verdict, reason = validate_proposal(proposal, {}, custom_validators=[custom_val])
    assert verdict == ValidationVerdict.REJECT
    assert "Custom validation failed: custom error reason" in reason


def test_dim_contract_flat_structure() -> None:
    """Contract can be flat instead of nested permissions/safety_rules."""
    contract = {
        "allowed_policy_types": ["TRADE"],
        "min_confidence_threshold": 0.8
    }
    proposal = _make_proposal(policy_kind="TRADE", confidence=0.85)
    verdict, _ = validate_proposal(proposal, {}, contract=contract)
    assert verdict == ValidationVerdict.ACCEPT

