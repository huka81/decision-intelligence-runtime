"""Tests for idempotency key and guard (DIR §7)."""

from dir_core.idempotency import (
    IdempotencyGuard,
    MemoryBackend,
    idempotency_key,
)


def test_idempotency_key_stable_under_key_reordering() -> None:
    k1 = idempotency_key("d", "step", {"b": 1, "a": 2})
    k2 = idempotency_key("d", "step", {"a": 2, "b": 1})
    assert k1 == k2


def test_idempotency_key_differs_for_step_or_dfid() -> None:
    base = idempotency_key("d", "s", {"x": 1})
    assert idempotency_key("d2", "s", {"x": 1}) != base
    assert idempotency_key("d", "s2", {"x": 1}) != base


def test_idempotency_guard_runs_once() -> None:
    calls: list[int] = []

    def work(x: int, y: int) -> dict:
        calls.append(1)
        return {"sum": x + y}

    guard = IdempotencyGuard(MemoryBackend())
    r1 = guard.run("df1", "add", {"x": 2, "y": 3}, work)
    r2 = guard.run("df1", "add", {"x": 2, "y": 3}, work)
    assert r1 == r2 == {"sum": 5}
    assert calls == [1]


def test_idempotency_guard_different_params_runs_again() -> None:
    guard = IdempotencyGuard(MemoryBackend())

    def work(n: int) -> dict:
        return {"n": n}

    assert guard.run("df1", "id", {"n": 1}, work) == {"n": 1}
    assert guard.run("df1", "id", {"n": 2}, work) == {"n": 2}
