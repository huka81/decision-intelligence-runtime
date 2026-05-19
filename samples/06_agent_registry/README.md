# 06 - Agent Registry

**Goal:** Demonstrate **Agent Discovery & Metadata Management** - maintaining a centralized registry of active agents with their capability contracts, priorities, and runtime metadata for multi-agent coordination and orchestration.

**DIR Alignment:** DIR Architectural Pattern §2.3 (Agent Discovery & Registry), ROA Manifesto §3.1 (Responsibility Contracts)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **Agent Registry** | §2.3 | Central catalog of all active agents in the system |
| **Capability Contract** | ROA §3.1 | Role, capabilities, supported operations |
| **Priority Management** | §2.3 | Numerical priority for conflict resolution and scheduling |
| **Agent Discovery** | §2.3 | `list_agents()` returns all active agent IDs |
| **Metadata Retrieval** | §2.3 | `get_agent_contract()` fetches full capability contract |
| **Version Tracking** | Implementation | Each agent contract includes version for evolution tracking |
| **Status Management** | Implementation | Agents marked ACTIVE/INACTIVE for lifecycle management |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Agent Registry                              │
│  "Central catalog of agents, capabilities, and coordination data"   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  register_agent(agent_id, contract, priority)               │    │
│  │  • Stores agent capability contract                         │    │
│  │  • Assigns priority for orchestration                       │    │
│  │  • Marks agent as ACTIVE                                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Capability Contract                                        │    │
│  │  {                                                          │    │
│  │    "role": "MONITOR|EXECUTOR|STRATEGIST",                   │    │
│  │    "capabilities": ["action1", "action2", ...],             │    │
│  │    "supported_instruments": [...],                          │    │
│  │    "version": "1.0.0"                                       │    │
│  │  }                                                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  list_agents() → [agent_id1, agent_id2, ...]                │    │
│  │  Discovery: Find all ACTIVE agents                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  get_agent_contract(agent_id) → contract                    │    │
│  │  Inspection: Retrieve full capability contract              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  get_agent_priority(agent_id) → priority_int                │    │
│  │  Coordination: Higher priority = higher precedence          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  SQLite Backend:                                                    │
│  • agent_id (PK), contract (JSON), priority, status                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## How to run

From repo root:

```bash
pip install -e .
python samples/06_agent_registry/run.py
```

## Scenario Demonstrated

### Agent Registration and Discovery
1. **Initialize storage**: `sqlite_storage` applies the canonical `schema.sql` DDL; `DecisionRuntime` exposes registry and `AuditStore`.
2. **Telemetry**: Each run gets a time-stamped `run_id` (`correlation_id` / `root_dfid`); `SIMULATION_START`, per-agent `AGENT_HANDSHAKE_ACCEPTED`, `SIMULATION_END` append to `decision_audit_events`.
3. **Handshake (register) high-priority monitor**:
   - `agent_id`: "agent_supervisor"
   - `role`: "MONITOR"
   - `capabilities`: ["halt_system", "audit_log"]
   - `priority`: 100 (highest in system)
   - `agent_version`: "1.0.0" (must satisfy runtime `supported_versions`, default `1.x`)
4. **Handshake standard executor**:
   - `agent_id`: "agent_trader_btc"
   - `role`: "EXECUTOR"
   - `capabilities`: ["place_order", "cancel_order"]
   - `supported_instruments`: ["BTC-USD"]
   - `priority`: 10
   - `agent_version`: "1.2.0" (same major as supervisor for default `1.x` constraint)
5. **Discovery**: List all active agents (may include bootstrap `__dir_kernel__` from audit bootstrap)
6. **Inspection**: Retrieve contract and priority for a specific agent
7. **Verification**: Confirm persistence and audit row count for this `run_id`

## Key Classes and Methods

```python
from dir_core import DecisionRuntime
from dir_core.storage import sqlite_storage

bundle = sqlite_storage("data/registry_run.sqlite")
runtime = DecisionRuntime(bundle)
registry = runtime.registry
audit = runtime.audit

hr = runtime.register_agent(
    "agent_trader_btc",
    {
        "role": "EXECUTOR",
        "capabilities": ["place_order", "cancel_order"],
        "supported_instruments": ["BTC-USD"],
        "version": "1.2.0",
    },
    "1.2.0",
    priority=10,
)
assert hr.accepted

agents = registry.list_agents()
contract = registry.get_agent_contract("agent_trader_btc")
priority = registry.get_agent_priority("agent_trader_btc")
```

SQLite table `agent_registry` is defined in `src/dir_core/storage/schema.sql` (JSON contract, priority, status `ACTIVE`/`SUSPENDED`/…, `agent_version`, `session_token`, timestamps). This sample stores agents under `data/registry_run.sqlite` (gitignored).

## Expected Output

```
======================================================================
Agent Registry Demonstration
======================================================================
Database: .../samples/06_agent_registry/data/registry_run.sqlite

[Registration] Handshake (register) agents...
   [OK] agent_supervisor handshake accepted
   [OK] agent_trader_btc handshake accepted

[Discovery] Active Agents: ['__dir_kernel__', 'agent_supervisor', 'agent_trader_btc']
   [OK] Listing successful

[Inspection] Checking 'agent_trader_btc'...
   Priority: 10
   Contract:
{'role': 'EXECUTOR', 'capabilities': [...], 'supported_instruments': ['BTC-USD'], 'version': '1.2.0'}

SUCCESS: Agent registry persisted and retrieved data correctly.
Audit events for this run (run_id / correlation_id): 4
```

## Why Agent Registry Matters

from dir_core Architectural Pattern §2.3 and ROA Manifesto §3.1:

> *"In a multi-agent system, agents must discover each other's capabilities without tight coupling. The Agent Registry provides a central catalog where agents declare their Capability Contracts during initialization. This enables dynamic orchestration, capability-based routing, and runtime introspection without hardcoded dependencies."*

### Key Insights:

1. **Capability Contracts**:
   - Declaration of what an agent **can do**, not how it does it
   - Includes role (MONITOR, EXECUTOR, STRATEGIST), capabilities, supported operations
   - Version tracking for safe evolution and compatibility checking
   - Similar to interface definitions in OOP or API contracts in microservices

2. **Dynamic Discovery**:
   - No hardcoded agent dependencies
   - Runtime queries: "Which agents can handle BTC-USD trades?"
   - Enables hot-swapping: replace agent without system restart
   - Supports A/B testing: run multiple agent versions simultaneously

3. **Priority-Based Coordination**:
   - Numerical priority for conflict resolution
   - Higher priority agents override lower priority in disputes
   - Supervisor agents (priority 100) can halt executor agents (priority 10)
   - Enables hierarchical decision-making (escalation chains)

4. **Status Management**:
   - Agents marked ACTIVE or INACTIVE
   - Lifecycle tracking: when agent registered, last update
   - Graceful shutdown: deactivate agent without deleting contract
   - Debugging: inspect inactive agents to understand past system states

5. **Centralized vs. Distributed**:
   - Current implementation: centralized SQLite registry
   - Production: could use distributed registry (etcd, Consul, ZooKeeper)
   - Tradeoff: simplicity vs. high availability

### Real-World Use Cases:

**Financial Trading Platform**:
```python
# Register specialized agents
registry.register_agent("agent_risk_monitor", {
    "role": "MONITOR",
    "capabilities": ["halt_trading", "adjust_limits"],
    "monitored_metrics": ["var", "drawdown", "leverage"]
}, priority=100)

registry.register_agent("agent_btc_trader", {
    "role": "EXECUTOR",
    "capabilities": ["place_order", "cancel_order"],
    "instruments": ["BTC-USD", "BTC-EUR"]
}, priority=10)

# Orchestration logic
if market_volatility > 0.8:
    # Find all executors and pause them
    for agent_id in registry.list_agents():
        contract = registry.get_agent_contract(agent_id)
        if contract.get("role") == "EXECUTOR":
            send_command(agent_id, "PAUSE")
```

**Cloud Infrastructure Orchestration**:
```python
registry.register_agent("agent_autoscaler", {
    "role": "STRATEGIST",
    "capabilities": ["scale_up", "scale_down"],
    "managed_services": ["api-gateway", "worker-pool"]
}, priority=50)

registry.register_agent("agent_cost_optimizer", {
    "role": "MONITOR",
    "capabilities": ["recommend_downsize", "flag_waste"],
    "optimization_targets": ["cost", "performance"]
}, priority=30)
```

**Insurance Claims Processing**:
```python
registry.register_agent("agent_fraud_detector", {
    "role": "MONITOR",
    "capabilities": ["flag_suspicious", "request_review"],
    "detection_methods": ["pattern", "anomaly", "network"]
}, priority=80)

registry.register_agent("agent_auto_approver", {
    "role": "EXECUTOR",
    "capabilities": ["approve_claim", "calculate_payout"],
    "claim_types": ["auto", "property"],
    "max_amount": 5000.0
}, priority=20)
```

### Orchestration Patterns Enabled:

1. **Capability-Based Routing**:
   ```python
   # Find agent that can handle specific instrument
   for agent_id in registry.list_agents():
       contract = registry.get_agent_contract(agent_id)
       instruments = contract.get("supported_instruments", [])
       if "BTC-USD" in instruments:
           route_decision_to(agent_id)
   ```

2. **Priority-Based Override**:
   ```python
   # Higher priority agent can override lower priority decisions
   proposals = get_all_proposals(dfid)
   proposals.sort(key=lambda p: registry.get_agent_priority(p.agent_id), reverse=True)
   final_decision = proposals[0]  # Highest priority wins
   ```

3. **Role-Based Filtering**:
   ```python
   # Only consult MONITORs for escalation decisions
   monitors = [
       agent_id for agent_id in registry.list_agents()
       if registry.get_agent_contract(agent_id).get("role") == "MONITOR"
   ]
   ```

4. **Version-Based Routing** (A/B Testing):
   ```python
   # Route 10% of traffic to new agent version
   contract = registry.get_agent_contract("agent_trader_btc_v2")
   if contract.get("version") == "2.1.0" and random.random() < 0.1:
       use_agent("agent_trader_btc_v2")
   else:
       use_agent("agent_trader_btc")
   ```

### Integration with DIR Pattern:

```
System Startup:
  → Agents initialize
  → Each agent calls registry.register_agent() with contract
  → Registry persists contracts in SQLite

Runtime Decision Flow:
  → Context arrives requiring decision
  → Orchestrator queries registry.list_agents()
  → Filters agents by capability/role
  → Routes context to matching agents
  → Agents emit proposals
  → Orchestrator uses priority for conflict resolution

Agent Shutdown:
  → Agent calls registry.deactivate(agent_id)
  → Registry marks status = INACTIVE
  → Future queries exclude this agent
```

### Comparison to Alternatives:

❌ **Hardcoded dependencies**: Brittle, can't add agents without code changes  
❌ **Service discovery only** (e.g., DNS): No capability metadata, just endpoints  
❌ **Message passing without registry**: Agents broadcast capabilities, inefficient  
✅ **Centralized Registry**: Fast lookups, metadata-rich, auditable registration history

The Agent Registry is the **phonebook** of the multi-agent system - it answers "Who can do what?" enabling dynamic, loosely-coupled orchestration.

