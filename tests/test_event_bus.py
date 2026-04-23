"""Tests for in-memory EventBus and factory (DIR Topologies §2)."""

import os
from unittest.mock import patch

import pytest

from dir_core.data_types import EventBusBackend, EventType
from dir_core.event_bus import (
    Event,
    EventBus,
    EventMetadata,
    LoggingEventBus,
    create_event_bus,
)


def test_subscribe_dispatch_notifies_listener() -> None:
    bus = EventBus()
    seen: list[dict] = []

    def cb(payload: dict) -> None:
        seen.append(payload)

    bus.subscribe(EventType.OBSERVATION, cb)
    ev = Event(
        type=EventType.OBSERVATION,
        payload={"k": 1},
        metadata=EventMetadata(),
    )
    n = bus.dispatch(ev)
    assert n == 1
    assert seen == [{"k": 1}]


def test_publish_convenience() -> None:
    bus = EventBus()
    acc: list[dict] = []
    bus.subscribe("CUSTOM_TOPIC", acc.append)
    assert bus.publish("CUSTOM_TOPIC", {"x": 2}) == 1
    assert acc == [{"x": 2}]
    assert bus.event_count == 1


def test_scope_filter_matches_target() -> None:
    bus = EventBus()
    broad: list[dict] = []
    scoped: list[dict] = []
    bus.subscribe(EventType.RISK_ALERT, broad.append, scope=None)
    bus.subscribe(EventType.RISK_ALERT, scoped.append, scope="BTC-USD")

    meta = EventMetadata(target_scope="ETH-USD")
    ev1 = Event(type=EventType.RISK_ALERT, payload={"a": 1}, metadata=meta)
    assert bus.dispatch(ev1) == 1
    assert broad == [{"a": 1}]
    assert scoped == []

    meta2 = EventMetadata(target_scope="BTC-USD")
    ev2 = Event(type=EventType.RISK_ALERT, payload={"b": 2}, metadata=meta2)
    assert bus.dispatch(ev2) == 2
    assert broad == [{"a": 1}, {"b": 2}]
    assert scoped == [{"b": 2}]


def test_scope_star_subscription_receives_all_targets() -> None:
    bus = EventBus()
    got: list[dict] = []
    bus.subscribe(EventType.NEWS, got.append, scope="*")
    n = bus.publish(
        EventType.NEWS,
        {"item": 1},
        metadata=EventMetadata(target_scope="ANY"),
    )
    assert n == 1
    assert got == [{"item": 1}]


def test_unsubscribe_removes_listener() -> None:
    bus = EventBus()

    def cb(p: dict) -> None:
        pass

    bus.subscribe(EventType.POLICY_PROPOSAL, cb)
    assert bus.subscription_count == 1
    bus.unsubscribe(EventType.POLICY_PROPOSAL, cb)
    assert bus.subscription_count == 0
    ev = Event(
        type=EventType.POLICY_PROPOSAL,
        payload={},
        metadata=EventMetadata(),
    )
    assert bus.dispatch(ev) == 0


def test_event_string_coerces_to_event_type_when_known() -> None:
    e = Event(type="OBSERVATION", payload={}, metadata=EventMetadata())
    assert e.type == EventType.OBSERVATION
    assert e.type_key == "OBSERVATION"


def test_event_custom_string_type_preserved() -> None:
    e = Event(type="MY_CUSTOM", payload={}, metadata=EventMetadata())
    assert e.type == "MY_CUSTOM"
    assert e.type_key == "MY_CUSTOM"


def test_listener_exception_does_not_block_others() -> None:
    bus = EventBus()
    ok: list[str] = []

    def bad(_: dict) -> None:
        raise RuntimeError("boom")

    def good(_: dict) -> None:
        ok.append("y")

    bus.subscribe(EventType.EXECUTION_RESULT, bad, scope=None)
    bus.subscribe(EventType.EXECUTION_RESULT, good, scope=None)
    ev = Event(
        type=EventType.EXECUTION_RESULT,
        payload={},
        metadata=EventMetadata(),
    )
    n = bus.dispatch(ev)
    assert n == 1
    assert ok == ["y"]


def test_create_event_bus_memory_default() -> None:
    bus = create_event_bus()
    assert isinstance(bus, EventBus)


def test_create_event_bus_with_logging_wraps() -> None:
    wrapped = create_event_bus(with_logging=True)
    assert isinstance(wrapped, LoggingEventBus)
    got: list[dict] = []
    wrapped.subscribe(EventType.FLOW_COMPLETED, got.append)
    wrapped.publish(
        EventType.FLOW_COMPLETED,
        {"done": True},
        metadata=EventMetadata(dfid="d1"),
    )
    assert len(wrapped.get_event_log()) == 1
    assert got == [{"done": True}]


def test_create_event_bus_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unknown backend"):
        create_event_bus("not-a-backend")


def test_create_event_bus_kafka_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Kafka"):
        create_event_bus(EventBusBackend.KAFKA)


def test_create_event_bus_pubsub_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="PubSub"):
        create_event_bus(EventBusBackend.PUBSUB)


def test_create_event_bus_respects_env_backend() -> None:
    with patch.dict(os.environ, {"EVENT_BUS_BACKEND": "memory"}):
        bus = create_event_bus()
        assert isinstance(bus, EventBus)
