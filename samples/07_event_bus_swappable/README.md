# 07 - Event Bus (Swappable) - EOAM Demonstration

**Goal:** Demonstrate the **Event-Oriented Agent Mesh (EOAM)** pattern from DIR Topologies §2, showing how multiple agents reactively collaborate through an event bus.

**DIR Alignment:** Topologies §2 (EOAM), §2.1 (Scope-Based Choreography), §2.3 (Economic Guardrails), §2.4 (Priority-Based Preemption)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **EOAM Choreography** | §2.1 | Agents subscribe to topics, react to events autonomously |
| **Scope-Based Routing** | §2.1 | `scope` parameter filters events to relevant agents |
| **Wake-up Predicates** | §2.3 | Low-cost heuristics prevent Token Burn (expensive LLM calls) |
| **Priority-Based Preemption** | §2.4 | Priority matrix selects winning proposal (Risk > Strategy) |
| **DFID Correlation** | §5.4 | Every event carries `dfid` in metadata for traceability |
| **Swappable Backend** | §10.2 | Factory pattern: `create_event_bus(backend="memory")` |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Event-Oriented Agent Mesh (EOAM)                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   OBSERVATION Event (with DFID)                                     │
│         │                                                           │
│         ▼                                                           │
│   ┌─────────────────────────────────────────────────────┐           │
│   │              EventBus (swappable)                   │           │
│   │   Scope: BTC-USD  │  Scope: ETH-USD  │  Scope: *    │           │
│   └─────────────────────────────────────────────────────┘           │
│         │                     │                  │                  │
│         ▼                     ▼                  ▼                  │
│   ┌──────────┐         ┌──────────┐       ┌──────────┐              │
│   │  Wake-up │         │  Wake-up │       │  (no     │              │
│   │ Predicate│         │ Predicate│       │ predicate│              │
│   └────┬─────┘         └────┬─────┘       └────┬─────┘              │
│        │ PASS               │ SKIP             │ PASS               │
│        ▼                    ✗                  ▼                    │
│   ┌──────────┐                           ┌──────────┐               │
│   │ Technical│                           │   Risk   │               │
│   │  Agent   │                           │  Monitor │               │
│   └────┬─────┘                           └────┬─────┘               │
│        │                                      │                     │
│        ▼                                      ▼                     │
│   ┌─────────────────────────────────────────────────────┐           │
│   │           PolicyProposal Collection                 │           │
│   └─────────────────────────────────────────────────────┘           │
│                          │                                          │
│                          ▼                                          │
│   ┌─────────────────────────────────────────────────────┐           │
│   │        Priority-Based Arbitration                   │           │
│   │   RISK_ALERT(1) > CLOSE(2) > OPEN(3) > HOLD(6)      │           │
│   └─────────────────────────────────────────────────────┘           │
│                          │                                          │
│                          ▼                                          │
│                   Winning Proposal                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## How to run

From repo root:

```bash
pip install -e .
python samples/07_event_bus_swappable/run.py
```

## Scenarios Demonstrated

### Scenario A: Multi-Agent Reactive Activation
- Three agents (Risk, Technical, Sentiment) subscribe to OBSERVATION events
- All agents activated in parallel when observation is published
- Proposals collected and arbitrated

### Scenario B: Risk Preemption
- High volatility triggers RISK_ALERT from risk monitor
- Priority matrix ensures RISK_ALERT (priority=1) wins over other proposals
- Demonstrates: "Safety always overrides strategy"

### Scenario C: Wake-up Predicates (Token Burn Prevention)
- Expensive LLM agent has wake-up predicates:
  - `significant_move`: only wake if price change > 1%
  - `btc_only`: only wake for BTC-USD
- Small moves (0.2%) → agent NOT activated (token saved)
- Large moves (2.5%) → agent activated

### Scenario D: Scope-Based Routing
- `btc_specialist` subscribes with `scope="BTC-USD"`
- `eth_specialist` subscribes with `scope="ETH-USD"`
- `global_risk` subscribes with `scope="*"` (broadcast)
- BTC event only reaches btc_specialist + global_risk

### Scenario E: Swappable Backend Pattern
- `LoggingEventBus` wraps `EventBus` for audit
- All events logged for compliance/debugging
- Same interface, different behavior

## Key Classes

```python
# EventMetadata - routing and tracing info
metadata = EventMetadata(
    dfid="abc-123",           # DecisionFlow correlation
    priority=1,               # Event priority
    source_agent="risk_mon",  # Who emitted
    target_scope="BTC-USD",   # Semantic routing filter
)

# Event with metadata
event = Event(
    type=EventType.OBSERVATION,
    payload={"price": 67500, "volatility": 0.03},
    metadata=metadata,
)

# Wake-up Predicate
predicate = WakeupPredicate(
    name="significant_move",
    condition=lambda p: abs(p.get("price_delta_pct", 0)) > 0.01
)

# Swappable backend factory
bus = create_event_bus(backend="memory", with_logging=True)
```

## Swapping for Kafka/PubSub

The `EventBusProtocol` defines the interface:

```python
class EventBusProtocol(Protocol):
    def subscribe(self, event_type, callback, scope=None) -> None: ...
    def unsubscribe(self, event_type, callback) -> None: ...
    def dispatch(self, event: Event) -> int: ...
    def publish(self, event_type, payload, metadata=None) -> int: ...
```

To implement Kafka backend:
1. Create `KafkaEventBus` implementing the protocol
2. Add to factory: `create_event_bus(backend="kafka")`
3. Set env: `EVENT_BUS_BACKEND=kafka`

## Expected Output

```
======================================================================
Event Bus Sample - Event-Oriented Agent Mesh (EOAM)
======================================================================

[SCENARIO A] Multi-agent reactive activation

  DFID: abc123...
  Proposals collected: 3
  Winner: SENTIMENT_BULLISH from sentiment_agent

----------------------------------------------------------------------

[SCENARIO B] Risk preemption - high volatility overrides strategy

  DFID: def456...
  Proposals: 3
  Winner: RISK_ALERT (risk alert preempts other proposals)

----------------------------------------------------------------------

[SCENARIO C] Wake-up predicates - preventing Token Burn

  Small move (0.2%):
    Proposals: 1
    Expensive agent stats: {'events_received': 1, 'activated': 0, 'suppressed': 1}

  Large move (2.5%):
    Proposals: 2
    Expensive agent stats: {'events_received': 2, 'activated': 1, 'suppressed': 1}
    → Token Burn prevented: 1 activations skipped

...
```

## Why EOAM Matters

From DIR Topologies §2:

> *"EOAM is a decentralized architectural pattern where autonomous agents collaborate through a reactive event substrate. It defines a system that is 'Decentralized in activation, centralized in authority.'"*

Key benefits:
- **Parallelism**: Agents reason concurrently
- **Resilience**: One agent failure doesn't stop others
- **Scalability**: Add agents without changing orchestration
- **Auditability**: DFID traces every decision flow
