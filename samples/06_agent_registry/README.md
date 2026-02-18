# 06 - Agent Registry

**Goal:** Demonstrate **Agent Discovery & Metadata Management** - maintaining a centralized registry of active agents with their capability contracts (manifests), priorities, and runtime metadata for multi-agent coordination and orchestration.

**DIR Alignment:** DIR Architectural Pattern §2.3 (Agent Discovery & Registry), ROA Manifesto §3.1 (Responsibility Contracts)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **Agent Registry** | §2.3 | Central catalog of all active agents in the system |
| **Agent Manifest** | ROA §3.1 | Capability contract: role, capabilities, supported operations |
| **Priority Management** | §2.3 | Numerical priority for conflict resolution and scheduling |
| **Agent Discovery** | §2.3 | `list_agents()` returns all active agent IDs |
| **Metadata Retrieval** | §2.3 | `get_agent_manifest()` fetches full capability contract |
| **Capability Contract** | ROA §3.1 | Declaration of what an agent can do (not implementation) |
| **Version Tracking** | Implementation | Each agent manifest includes version for evolution tracking |
| **Status Management** | Implementation | Agents marked ACTIVE/INACTIVE for lifecycle management |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Agent Registry                              │
│  "Central catalog of agents, capabilities, and coordination data"   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  register_agent(agent_id, manifest, priority)               │    │
│  │  • Stores agent capabilities (manifest)                     │    │
│  │  • Assigns priority for orchestration                       │    │
│  │  • Marks agent as ACTIVE                                    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Agent Manifest (Capability Contract)                       │    │
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
│  │  get_agent_manifest(agent_id) → manifest                    │    │
│  │  Inspection: Retrieve full capability contract              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  get_agent_priority(agent_id) → priority_int                │    │
│  │  Coordination: Higher priority = higher precedence          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  SQLite Backend:                                                    │
│  • agent_id (PK), manifest (JSON), priority, status, updated_at     │
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
1. **Initialize Registry**: Create SQLite-backed AgentRegistry
2. **Register High-Priority Monitor**:
   - `agent_id`: "agent_supervisor"
   - `role`: "MONITOR"
   - `capabilities`: ["halt_system", "audit_log"]
   - `priority`: 100 (highest in system)
   - `version`: "1.0.0"
3. **Register Standard Executor**:
   - `agent_id`: "agent_trader_btc"
   - `role`: "EXECUTOR"
   - `capabilities`: ["place_order", "cancel_order"]
   - `supported_instruments`: ["BTC-USD"]
   - `priority`: 10 (standard priority)
   - `version`: "2.1.0"
4. **Discovery**: List all active agents
5. **Inspection**: Retrieve manifest and priority for specific agent
6. **Verification**: Confirm data persistence and retrieval

## Key Classes and Methods

```python
from dir.agent_registry import AgentRegistry

# Initialize
registry = AgentRegistry(db_path)

# Register Agent with Manifest
registry.register_agent(
    agent_id="agent_trader_btc",
    manifest={
        "role": "EXECUTOR",
        "capabilities": ["place_order", "cancel_order"],
        "supported_instruments": ["BTC-USD"],
        "version": "2.1.0"
    },
    priority=10
)

# Discovery: List all active agents
agents = registry.list_agents()
# Returns: ["agent_supervisor", "agent_trader_btc", ...]

# Inspection: Get agent manifest
manifest = registry.get_agent_manifest("agent_trader_btc")
# Returns: {"role": "EXECUTOR", "capabilities": [...], ...}

# Coordination: Get agent priority
priority = registry.get_agent_priority("agent_trader_btc")
# Returns: 10
```

## Database Schema

```sql
CREATE TABLE agent_registry (
    agent_id TEXT PRIMARY KEY,
    manifest JSON,
    priority INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ACTIVE',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Expected Output

```
======================================================================
Agent Registry Demonstration
======================================================================
Database: D:\...\samples\06_agent_registry\data\registry.db

[Registration] Registering agents...
INFO Registered agent: agent_supervisor (priority=100)
INFO Registered agent: agent_trader_btc (priority=10)

[Discovery] Active Agents: ['agent_supervisor', 'agent_trader_btc']
   ✅ Listing successful

[Inspection] Checking 'agent_trader_btc'...
   Priority: 10
   Manifest:
   {
     'role': 'EXECUTOR',
     'capabilities': ['place_order', 'cancel_order'],
     'supported_instruments': ['BTC-USD'],
     'version': '2.1.0'
   }

SUCCESS: Agent registry persisted and retrieved data correctly.
```

## Why Agent Registry Matters

From DIR Architectural Pattern §2.3 and ROA Manifesto §3.1:

> *"In a multi-agent system, agents must discover each other's capabilities without tight coupling. The Agent Registry provides a central catalog where agents declare their Capability Contracts (manifests) during initialization. This enables dynamic orchestration, capability-based routing, and runtime introspection without hardcoded dependencies."*

### Key Insights:

1. **Capability Contracts (Manifests)**:
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
   - Graceful shutdown: deactivate agent without deleting manifest
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
        manifest = registry.get_agent_manifest(agent_id)
        if manifest.get("role") == "EXECUTOR":
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
       manifest = registry.get_agent_manifest(agent_id)
       instruments = manifest.get("supported_instruments", [])
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
       if registry.get_agent_manifest(agent_id).get("role") == "MONITOR"
   ]
   ```

4. **Version-Based Routing** (A/B Testing):
   ```python
   # Route 10% of traffic to new agent version
   manifest = registry.get_agent_manifest("agent_trader_btc_v2")
   if manifest.get("version") == "2.1.0" and random.random() < 0.1:
       use_agent("agent_trader_btc_v2")
   else:
       use_agent("agent_trader_btc")
   ```

### Integration with DIR Pattern:

```
System Startup:
  → Agents initialize
  → Each agent calls registry.register_agent() with manifest
  → Registry persists manifests in SQLite

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
