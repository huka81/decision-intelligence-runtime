# 04 - Context Store

**Goal:** Demonstrate **Layered Context Management** - separating ephemeral session data (DFID-scoped) from authoritative agent state (agent_id-scoped) to enable clean context compilation for decision-making.

**DIR Alignment:** DIR Architectural Pattern §8 (Context Management), DIR Topologies §2.2 (ContextSnapshot)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **Layered Context** | §8.1 | Four architectural layers: Session, State, Memory, Artifacts |
| **Session Layer** | §8.2 | Ephemeral data linked to current DecisionFlow (DFID) |
| **State Layer** | §8.3 | Authoritative long-lived agent data (policy versions, trajectory) |
| **Context Compilation** | §8.4 | `compile_working_context()` assembles immutable snapshot |
| **DFID Correlation** | §5.4 | Session data scoped to specific decision flow |
| **Agent State Isolation** | §3.4 | Each agent has independent state storage |
| **Persistence** | §8, `schema.sql` | SQLite `flow_context`, `agent_state`; full DDL via `sqlite_storage` |
| **Registry FK** | §2.3, §8 | Agent handshake before state/session so FK to `agent_registry` holds |
| **Telemetry** | Observability | Append-only `decision_audit_events` with `root_dfid` / `correlation_id` per run |
| **Immutable Snapshot** | §8.4 | Compiled context is frozen view for decision consistency |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Context Store                               │
│  "Multi-layered context management for decision intelligence"       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 1: SESSION (Ephemeral)                               │    │
│  │  Scope: DecisionFlow (dfid)                                 │    │
│  │  Examples: request_id, user_intent, input_payload           │    │
│  │  Lifetime: Single decision flow                             │    │
│  │  Storage: `flow_context` (canonical schema)                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 2: STATE (Authoritative)                             │    │
│  │  Scope: Agent (agent_id)                                    │    │
│  │  Examples: policy_version, risk_threshold, allowed_markets  │    │
│  │  Lifetime: Long-lived (persists across flows)               │    │
│  │  Storage: `agent_state`                                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 3: MEMORY (Long-term) [Stub in MVP]                  │    │
│  │  Scope: Historical decisions, embeddings                    │    │
│  │  Examples: Vector DB, archived trajectories                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 4: ARTIFACTS (Reference) [Stub in MVP]               │    │
│  │  Scope: Static documents, rules, schemas                    │    │
│  │  Examples: Compliance docs, API specs                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│                            ↓                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  compile_working_context(agent_id, dfid)                    │    │
│  │  → Immutable snapshot containing all layers                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation Note

The Memory and Artifacts layers are stubs (return `{}`) in the current implementation.
Full implementation requires integration with vector DB / archival storage for Memory,
and RAG / static docs for Artifacts. See DIR §8.1, ROA §7.2 for layer definitions.

## How to run

From repo root:

```bash
pip install -e .
python samples/04_context_store/run.py
```

## Scenario Demonstrated

### Layer Population and Compilation
1. **Initialize**: `sqlite_storage` + `DecisionRuntime`; handshake registers the agent (`agent_risk_analyzer_v1`).
2. **Audit**: Time-stamped `run_id` as `root_dfid` / `correlation_id`; events include `SIMULATION_START`, `AGENT_STATE_UPDATED`, `CONTEXT_SESSION_UPDATED`, `WORKING_CONTEXT_COMPILED`, `SIMULATION_END`.
3. **Populate State** (`agent_state`): policy_version, risk_threshold, allowed_markets, last_audit
4. **Populate Session** (`flow_context`), passing `agent_id` so `decision_flows` rows satisfy FKs.
5. **Compile** `compile_working_context(agent_id, dfid)` → session + state + stubs.
6. **Verification**: Expected fields present; audit row count printed for this `run_id`.

Persistence file: `data/context_run.sqlite` (gitignored).

## Key Classes and Methods

```python
from dir_core.context_store import ContextStore

# Initialize
store = ContextStore(db_path)

# Layer 1: Session (Ephemeral - DFID scoped)
store.update_session(dfid, {
    "request_id": "req_123",
    "user_intent": "check_risk",
    "input_payload": {"symbol": "BTC-USD", "amount": 5.0}
})
session_data = store.get_session(dfid)

# Layer 2: State (Authoritative - Agent scoped)
store.update_state(agent_id, {
    "policy_version": "2.1.0",
    "risk_threshold": 0.75,
    "allowed_markets": ["BTC-USD", "ETH-USD"]
})
state_data = store.get_state(agent_id)

# Compile Working Context (Immutable Snapshot)
working_context = store.compile_working_context(agent_id, dfid)
# Returns:
# {
#   "meta": {"agent_id": "...", "dfid": "...", "source": "ContextStore"},
#   "session": {...},  # Ephemeral data
#   "state": {...},    # Authoritative data
#   "memory": {},      # Stub for MVP
#   "artifacts": {}    # Stub for MVP
# }
```

## Database Schema

```sql
-- Session Layer (Ephemeral)
CREATE TABLE context_session (
    dfid TEXT PRIMARY KEY,
    data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- State Layer (Authoritative)
CREATE TABLE context_state (
    agent_id TEXT PRIMARY KEY,
    data JSON,
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Expected Output

```
======================================================================
Context Store Demonstration
======================================================================
Database: D:\...\samples\04_context_store\data\context.db

[Setup] Agent=agent_risk_analyzer_v1, DFID=df-12a3b4c5...
[State] Setting authoritative state...
[Session] Setting ephemeral session data...

[Compiler] Building Working Context...

------------------------------
WORKING CONTEXT CONTAINS:
------------------------------
{
  'meta': {
    'agent_id': 'agent_risk_analyzer_v1',
    'dfid': 'df-12a3b4c5...',
    'source': 'ContextStore'
  },
  'session': {
    'request_id': 'req_123',
    'user_intent': 'check_risk',
    'input_payload': {
      'symbol': 'BTC-USD',
      'amount': 5.0
    }
  },
  'state': {
    'policy_version': '2.1.0',
    'risk_threshold': 0.75,
    'allowed_markets': ['BTC-USD', 'ETH-USD'],
    'last_audit': '2023-10-27'
  },
  'memory': {},
  'artifacts': {}
}
------------------------------

SUCCESS: Context compiled correctly from state and session layers.
```

## Why Layered Context Matters

from dir_core Architectural Pattern §8:

> *"Context management is the foundation of intelligent decision-making. Agents need access to both ephemeral request data (session) and long-lived configuration (state), but mixing these layers creates confusion. The ContextStore separates concerns: session data is DFID-scoped and disposable, state data is agent-scoped and authoritative. The compiler assembles an immutable snapshot ensuring consistent context throughout the decision lifecycle."*

### Key Insights:

1. **Separation of Concerns**:
   - **Session**: Transient request data, changes per decision flow
   - **State**: Durable agent configuration, evolves slowly
   - Clear boundaries prevent accidental overwrites

2. **DFID Correlation**:
   - Session data is automatically scoped to DecisionFlow
   - Multiple concurrent flows can't interfere with each other
   - Clean separation of parallel decision processes

3. **Agent Isolation**:
   - Each agent has independent state storage
   - State updates don't affect other agents
   - Supports multi-agent systems with isolated configurations

4. **Immutable Snapshots**:
   - `compile_working_context()` returns frozen view
   - Context can't change mid-decision
   - Enables reproducible decisions and audit trails

5. **Extensibility** (Future Layers):
   - **Memory**: Vector DB for semantic retrieval of historical decisions
   - **Artifacts**: Static reference documents, compliance rules, schemas
   - Design accommodates future context sources without breaking existing code

### Real-World Use Cases:

- **Financial Trading**: Session = current market tick, State = agent's risk limits
- **Insurance Underwriting**: Session = application details, State = underwriting rules version
- **Fraud Detection**: Session = transaction data, State = learned fraud patterns
- **Customer Support**: Session = current query, State = customer history and preferences

### Comparison to Alternatives:

❌ **Single global context**: No separation, agents interfere, hard to debug  
❌ **Per-request monolith**: No agent memory, can't learn or evolve  
✅ **Layered ContextStore**: Clean separation, concurrent-safe, auditable

