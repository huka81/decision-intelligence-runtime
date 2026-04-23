"""Tests for dir.wakeup module."""

from dir_core.wakeup import (
    WakeupPredicate,
    is_relevant_instrument,
    price_change_significant,
    should_wake,
    volatility_elevated,
)


def test_price_change_significant() -> None:
    assert price_change_significant({"price_delta_pct": 0.01}) is True
    assert price_change_significant({"price_delta_pct": 0.001}) is False
    assert price_change_significant({"price_delta_pct": -0.02}) is True
    assert price_change_significant({}) is False


def test_volatility_elevated() -> None:
    assert volatility_elevated({"volatility": 0.05}) is True
    assert volatility_elevated({"volatility": 0.01}) is False
    assert volatility_elevated({}) is False


def test_is_relevant_instrument() -> None:
    assert is_relevant_instrument({"instrument": "BTC-USD"}, ["BTC-USD", "ETH-USD"]) is True
    assert is_relevant_instrument({"instrument": "XRP-USD"}, ["BTC-USD", "ETH-USD"]) is False
    assert is_relevant_instrument({}, ["BTC-USD"]) is False


def test_wakeup_predicate_evaluate() -> None:
    pred = WakeupPredicate("test", lambda p: p.get("x", 0) > 5)
    assert pred.evaluate({"x": 10}) is True
    assert pred.evaluate({"x": 1}) is False


def test_should_wake_all_pass() -> None:
    preds = [
        WakeupPredicate("a", lambda p: True),
        WakeupPredicate("b", lambda p: True),
    ]
    assert should_wake({"x": 1}, preds) is True


def test_should_wake_one_fails() -> None:
    preds = [
        WakeupPredicate("a", lambda p: True),
        WakeupPredicate("b", lambda p: p.get("x", 0) > 5),
    ]
    assert should_wake({"x": 1}, preds) is False
    assert should_wake({"x": 10}, preds) is True


def test_should_wake_empty() -> None:
    assert should_wake({"x": 1}, []) is True

