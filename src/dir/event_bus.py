"""
In-memory Event Bus for agent/runtime communication.

Swappable: same subscribe/dispatch interface can be backed by Kafka/PubSub later.
See docs/00-do-not-publish/event_bus.py for original reference.

DIR Topologies §2: Event-Oriented Agent Mesh (EOAM) uses event bus for
decentralized agent activation. Agents subscribe to topics matching their
Responsibility Contract scope.
"""

import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Canonical event types for EOAM lifecycle (DIR Topologies §2.4)."""

    # Observation layer - triggers flows
    OBSERVATION = "OBSERVATION"
    MARKET_SIGNAL = "MARKET_SIGNAL"
    NEWS = "NEWS"
    RISK_ALERT = "RISK_ALERT"
    
    # Agent reasoning layer
    POLICY_PROPOSAL = "POLICY_PROPOSAL"
    ESCALATION = "ESCALATION"
    
    # Runtime validation layer
    VALIDATION_RESULT = "VALIDATION_RESULT"
    VALIDATION_REJECTED = "VALIDATION_REJECTED"
    
    # Execution layer
    EXECUTION_INTENT = "EXECUTION_INTENT"
    EXECUTION_RESULT = "EXECUTION_RESULT"
    
    # System events
    AGENT_ACTIVATED = "AGENT_ACTIVATED"
    FLOW_COMPLETED = "FLOW_COMPLETED"


@dataclass
class EventMetadata:
    """Metadata for event routing and tracing (DIR Topologies §2.2)."""
    
    dfid: Optional[str] = None  # DecisionFlow ID for correlation
    priority: int = 5  # 1=highest, 10=lowest
    source_agent: Optional[str] = None
    target_scope: Optional[str] = None  # e.g., "BTC-USD", "*" for broadcast
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context_snapshot_id: Optional[str] = None  # For JIT verification


@dataclass
class Event:
    """Event with type, payload, and metadata (DIR Topologies §2.2)."""

    type: Union[str, EventType]
    payload: Dict[str, Any]
    metadata: EventMetadata = field(default_factory=EventMetadata)
    
    def __post_init__(self):
        if isinstance(self.type, str):
            try:
                self.type = EventType(self.type)
            except ValueError:
                pass  # Allow custom string types
    
    @property
    def type_key(self) -> str:
        return self.type.value if isinstance(self.type, EventType) else self.type


# =============================================================================
# EventBus Protocol (for swappable backends)
# =============================================================================


class EventBusProtocol(Protocol):
    """Protocol for swappable EventBus implementations (DIR §10.2)."""
    
    def subscribe(
        self, 
        event_type: Union[EventType, str], 
        callback: Callable[[Dict[str, Any]], None],
        scope: Optional[str] = None,
    ) -> None:
        """Subscribe to events of given type, optionally filtered by scope."""
        ...
    
    def unsubscribe(
        self, 
        event_type: Union[EventType, str], 
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Remove subscription."""
        ...
    
    def dispatch(self, event: Event) -> int:
        """Dispatch event to subscribers. Returns number of listeners notified."""
        ...
    
    def publish(
        self, 
        event_type: Union[EventType, str], 
        payload: Dict[str, Any],
        metadata: Optional[EventMetadata] = None,
    ) -> int:
        """Convenience: create Event and dispatch."""
        ...


# =============================================================================
# In-Memory Implementation
# =============================================================================


@dataclass
class Subscription:
    """Subscription with optional scope filter."""
    callback: Callable[[Dict[str, Any]], None]
    scope: Optional[str] = None  # None = all, "*" = broadcast, "BTC-USD" = specific


class EventBus:
    """
    Synchronous in-memory EventBus implementing EventBusProtocol.
    Replace with a Kafka/PubSub-backed implementation using the same interface.
    
    Features:
    - Scope-based filtering (EOAM semantic routing)
    - Priority ordering
    - DFID correlation logging
    """

    def __init__(self, name: str = "InMemory") -> None:
        self._name = name
        self._listeners: Dict[str, List[Subscription]] = {}
        self._lock = threading.Lock()
        self._event_count = 0

    def subscribe(
        self, 
        event_type: Union[EventType, str], 
        callback: Callable[[Dict[str, Any]], None],
        scope: Optional[str] = None,
    ) -> None:
        key = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            if key not in self._listeners:
                self._listeners[key] = []
            self._listeners[key].append(Subscription(callback=callback, scope=scope))
            logger.debug("[%s] Subscribed to %s (scope=%s)", self._name, key, scope)

    def unsubscribe(
        self, 
        event_type: Union[EventType, str], 
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        key = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            if key in self._listeners:
                self._listeners[key] = [s for s in self._listeners[key] if s.callback != callback]
                if not self._listeners[key]:
                    del self._listeners[key]

    def dispatch(self, event: Event) -> int:
        key = event.type_key
        target_scope = event.metadata.target_scope
        dfid = event.metadata.dfid
        
        with self._lock:
            all_subs = list(self._listeners.get(key, []))
        
        # Filter by scope
        matching_subs = []
        for sub in all_subs:
            if sub.scope is None or sub.scope == "*":
                matching_subs.append(sub)
            elif target_scope and sub.scope == target_scope:
                matching_subs.append(sub)
        
        dfid_prefix = f"[DFID={dfid}] " if dfid else ""
        logger.info("%s[%s] Dispatching %s to %d/%d listeners (scope=%s)", 
                   dfid_prefix, self._name, key, len(matching_subs), len(all_subs), target_scope)
        
        notified = 0
        for sub in matching_subs:
            try:
                sub.callback(event.payload)
                notified += 1
            except Exception:
                logger.exception("%sEventBus listener error for %s", dfid_prefix, key)
        
        self._event_count += 1
        return notified

    def publish(
        self, 
        event_type: Union[EventType, str], 
        payload: Dict[str, Any],
        metadata: Optional[EventMetadata] = None,
    ) -> int:
        """Convenience: create Event and dispatch."""
        event = Event(type=event_type, payload=payload, metadata=metadata or EventMetadata())
        return self.dispatch(event)
    
    @property
    def event_count(self) -> int:
        return self._event_count
    
    @property
    def subscription_count(self) -> int:
        with self._lock:
            return sum(len(subs) for subs in self._listeners.values())


# =============================================================================
# Logging Wrapper (for debugging)
# =============================================================================


class LoggingEventBus:
    """Wrapper that logs all events for debugging/audit."""
    
    def __init__(self, wrapped: EventBus):
        self._wrapped = wrapped
        self._event_log: List[Event] = []
    
    def subscribe(self, *args, **kwargs) -> None:
        return self._wrapped.subscribe(*args, **kwargs)
    
    def unsubscribe(self, *args, **kwargs) -> None:
        return self._wrapped.unsubscribe(*args, **kwargs)
    
    def dispatch(self, event: Event) -> int:
        self._event_log.append(event)
        logger.info("[AUDIT] Event logged: type=%s dfid=%s", 
                   event.type_key, event.metadata.dfid)
        return self._wrapped.dispatch(event)
    
    def publish(self, event_type, payload, metadata=None) -> int:
        event = Event(type=event_type, payload=payload, metadata=metadata or EventMetadata())
        return self.dispatch(event)
    
    def get_event_log(self) -> List[Event]:
        return self._event_log.copy()
    
    @property
    def event_count(self) -> int:
        return self._wrapped.event_count


# =============================================================================
# Factory (swappable backend selection)
# =============================================================================


def create_event_bus(backend: Optional[str] = None, with_logging: bool = False) -> EventBus:
    """Factory for creating EventBus instances.
    
    Args:
        backend: "memory" (default), or future: "kafka", "pubsub"
        with_logging: Wrap in LoggingEventBus for audit
    
    Environment:
        EVENT_BUS_BACKEND: Override backend selection
    """
    backend = backend or os.environ.get("EVENT_BUS_BACKEND", "memory")
    
    if backend == "memory":
        bus = EventBus(name="InMemory")
    elif backend == "kafka":
        # Future: return KafkaEventBus()
        raise NotImplementedError("Kafka backend not yet implemented")
    elif backend == "pubsub":
        # Future: return PubSubEventBus()
        raise NotImplementedError("PubSub backend not yet implemented")
    else:
        raise ValueError(f"Unknown backend: {backend}")
    
    if with_logging:
        return LoggingEventBus(bus)
    
    return bus
