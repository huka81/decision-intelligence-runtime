"""Tests for dir.jit module."""

from dir_core.data_types import ValidationVerdict
from dir_core.jit import JITStateVerifier, verify_drift


def test_verify_drift_no_drift() -> None:
    ok, reason = verify_drift(
        {"status": "clean", "score": 0.1},
        {"status": "clean", "score": 0.1},
        keys_to_compare=["status", "score"],
    )
    assert ok is True
    assert reason == ""


def test_verify_drift_detected() -> None:
    ok, reason = verify_drift(
        {"status": "clean"},
        {"status": "compromised"},
        keys_to_compare=["status"],
    )
    assert ok is False
    assert "STATE_DRIFT" in reason
    assert "clean" in reason
    assert "compromised" in reason


def test_verify_drift_tolerance() -> None:
    ok, _ = verify_drift(
        {"price": 100.0},
        {"price": 100.5},
        keys_to_compare=["price"],
        tolerance={"price": 1.0},
    )
    assert ok is True

    ok2, reason = verify_drift(
        {"price": 100.0},
        {"price": 102.0},
        keys_to_compare=["price"],
        tolerance={"price": 1.0},
    )
    assert ok2 is False
    assert "STATE_DRIFT" in reason


def test_jit_state_verifier() -> None:
    v = JITStateVerifier()
    verdict, reason = v.verify(
        {"status": "clean"},
        {"status": "clean"},
        keys_to_compare=["status"],
    )
    assert verdict == ValidationVerdict.ACCEPT
    assert "no state drift" in reason

    verdict2, reason2 = v.verify(
        {"status": "clean"},
        {"status": "compromised"},
        keys_to_compare=["status"],
    )
    assert verdict2 == ValidationVerdict.REJECT
    assert "STATE_DRIFT" in reason2 or "drift" in reason2.lower()

