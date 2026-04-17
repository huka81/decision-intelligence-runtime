# dir-core: Decision Intelligence Runtime

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)]()
[![Status](https://img.shields.io/badge/status-Initial_Release-orange.svg)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)]()

`dir-core` is the core Python package for the **Decision Intelligence Runtime (DIR)** and **Responsibility-Oriented Agents (ROA)** architecture.

This v0.1.0 initial release is a functional demonstration of the architectural patterns described in the ROA Manifesto and DIR architecture documents. It provides the deterministic "Kernel Space" infrastructure required to safely deploy probabilistic AI agents, ensuring that intelligence is constrained by strict governance, idempotency, and auditability.

---

## Core Concept: Architecture over Prompt Engineering

The framework shifts the paradigm of AI development from prompt engineering to systems engineering. It enforces a strict separation between two spaces:

- **User Space (Agents):** Probabilistic reasoning, intent formulation, and context interpretation. This is where LLMs operate.
- **Kernel Space (DIR):** Deterministic validation, state management, and execution orchestration. This is what `dir-core` provides.

Every agent proposal (`PolicyProposal`) must pass through the Decision Integrity Module (DIM) before it can become an authorized `ExecutionIntent`. The DIM verdict is the sole execution gate. No proposal bypasses it.

---

## What Is Included in v0.1.0

This release provides a foundational set of primitives for building governed AI systems.

### DecisionRuntime Facade

`DecisionRuntime` is the single entry point that wires a `StorageBundle` to all kernel services. It exposes `register_agent` and `evaluate_proposal` as the two primary operations, and provides direct access to `registry`, `context_store`, `escalation`, and `audit` for advanced orchestration.

### Decision Integrity Module (DIM)

`validate_proposal` performs deterministic validation of agent proposals against JSON Schema definitions, Role-Based Access Control (RBAC) rules, TTL boundaries, allowed agent lists, and custom validator callables injected at call time.

### Pluggable Storage Bundle

Out-of-the-box support for two built-in backends:

- `memory_storage()` -- ephemeral, in-process storage suitable for testing and quick-start scenarios.
- `sqlite_storage(path)` -- file-backed SQLite persistence with no external service dependencies.

Both backends implement the same set of typed storage protocols (`AgentRegistryStorage`, `ContextStorage`, `DecisionAuditStorage`, and others). Swapping to PostgreSQL requires only implementing those protocols and passing a custom `StorageBundle`.

### DecisionFlow ID (DFID) Correlation

`new_dfid()` and `new_dfid_with_parent(parent_dfid)` generate structured identifiers that tag every operation in a decision lifecycle, from observation to execution, enabling end-to-end traceability across all kernel subsystems.

### Agent Registry

`AgentRegistry` manages active agents, their `ResponsibilityContract` capability declarations, and performs SemVer handshakes to enforce runtime-agent compatibility before any proposal is accepted.

### Context Store

`ContextStore` provides multi-layered storage that gives agents isolated `Session` (ephemeral, per-DFID) and `State` (authoritative, per-agent) data. Both layers are compiled into a single working context before DIM validation.

### Idempotency Guard

`IdempotencyGuard` provides deterministic protection against double-execution using a `SHA256(dfid | step_id | canonical_params)` key. Both in-memory and SQLite backends are included.

### Escalation Manager

`EscalationManager` implements a governed Human-in-the-Loop (HITL) system with a token-bucket budget that prevents alert fatigue by rate-limiting escalation requests per configured time window.

### Resource Lock Manager

`ResourceLockManager` provides semantic reservation locks for shared resources such as capital budgets or API throughput quotas. Locks are acquired in linear alphabetical order to prevent deadlocks.

### JIT State Verifier

`JITStateVerifier` and `verify_drift` perform fast-pass drift checks immediately before execution to prevent Time-of-Check to Time-of-Use (TOCTOU) vulnerabilities when the live state may have changed since the proposal was formulated.

### Event Bus (Topology A -- EOAM)

`EventBus` and `create_event_bus` support multi-agent event mesh topologies with priority-based arbitration. The default implementation is synchronous and in-process.

### Proof-Carrying Intent (Topology C -- DL+PCI)

`compute_evidence_hash`, `ProofChecker`, and `ProofCarryingIntent` support Zero Trust decision trails where agents submit cryptographic evidence alongside their proposals, which the DIM recomputes and verifies independently.

### Additional Components

- `IntentRetryGovernor` -- caps retry loops over DIM or LLM reasoning with a configurable hard limit and a terminal `REASONING_EXHAUSTION` tag.
- `SagaCompensation` -- structured rollback of multi-step side effects.
- `DecisionLedger` -- append-only PCI-signed record of every decision for full audit trail scenarios.
- `WakeupPredicate` and `should_wake` -- Token-Burn prevention predicates for EOAM agent meshes.
- `FlowStatus` and `transition` -- deterministic lifecycle state machine for `DecisionFlow` entities.
- Full Pydantic model definitions for all core domain types: `PolicyProposal`, `ExecutionIntent`, `ResponsibilityContract`, `ContextSnapshot`, `DecisionFlow`, and others.

---

## Known Limitations and Simplifications in v0.1.0

This is an MVP release intended to demonstrate architectural feasibility. The following simplifications are intentional and documented here so that users can make informed decisions before deploying to production.

### Context Store Epistemic Longevity Stubs

The architecture specifies four context layers. In this release, the `Memory` layer (long-term associative recall) and the `Artifacts` layer (RAG and reference documents) are implemented as empty stubs returning `{}`. Meaningful long-term agent memory requires integrating an external vector database and is deferred to a future release.

### DIM ExecutionIntent Construction

`validate_proposal` evaluates a proposal and returns a `ValidationResult` tuple containing a verdict and a reason. It does not yet construct and freeze a formally sealed `ExecutionIntent` artifact inside the kernel. Execution dispatch responsibility currently rests with client code that receives the verdict. A fully kernel-managed `ExecutionIntent` lifecycle will be introduced in a subsequent release.

### Topology C Cryptography (DL+PCI)

The `compute_evidence_hash` function for Proof-Carrying Intents uses basic string concatenation of the form `f"{dfid}{context_hash}{contract_hash}{proposal_params}"`. This lacks secure length-prefixed delimiters, which makes it susceptible to hash collision attacks if component strings are attacker-controlled. It also substitutes proposal parameters for the rule-set hash for this MVP. This implementation demonstrates the concept only and must be hardened before use in any financial auditing or regulated context.

### Manual Post-Execution Governance

The framework provides `set_agent_status(agent_id, status="SUSPENDED")` as a mechanism to halt a misbehaving agent. However, the asynchronous rolling-window monitors required to detect Agent Drift autonomously over time are not included in this release. Drift detection logic must be implemented externally and integrated through the storage protocols.

### Synchronous Event Bus

The default `EventBus` for Topology A (EOAM) is an in-memory, thread-locked synchronous implementation. For production multi-agent meshes operating across process or service boundaries, the `EventBusProtocol` must be re-implemented using a message broker such as Apache Kafka or Google Pub/Sub. The protocol is stable and designed to be swapped.

### SQLite Concurrency Under Load

`SqliteResourceLockStorage` handles concurrent lock contentions by catching `sqlite3.OperationalError` and retrying with a `time.sleep` loop. Under heavy concurrent load this blocks threads ungracefully and does not scale. For production workloads with high lock contention, replace with a PostgreSQL-backed implementation that uses advisory locks or a dedicated coordination service.

---

## Quick Start

### Installation

```bash
pip install dir-runtime
```

With optional PostgreSQL support:

```bash
pip install "dir-runtime[postgres]"
```

### Minimal Usage

The following example shows the complete minimal flow: bootstrap the runtime, register an agent, submit a proposal, and gate execution on the DIM verdict.

```python
from dir_core import DecisionRuntime, PolicyProposal, new_dfid
from dir_core.storage import memory_storage

# Initialize the runtime with in-memory storage (no external dependencies)
runtime = DecisionRuntime(memory_storage())

# Register the agent and its ResponsibilityContract before any proposal
contract = {
    "agent_id": "trading_bot_01",
    "role": "EXECUTOR",
    "mission": "Execute ETH-USD trades within approved risk parameters.",
    "authorized_instruments": ["ETH-USD"],
    "allowed_policy_types": ["BUY", "SELL", "HOLD"],
    "escalate_on_uncertainty": 0.7,
    "max_drawdown_limit": 0.05,
    "wake_up_threshold_pct": 0.5,
    "parent_agent_id": None,
}
handshake = runtime.register_agent("trading_bot_01", contract, agent_version="1.0.0")
assert handshake.accepted, f"Handshake rejected: {handshake.reason}"

# Build a proposal (this would normally come from the LLM reasoning cycle)
proposal = PolicyProposal(
    dfid=new_dfid(),
    agent_id="trading_bot_01",
    policy_kind="BUY",
    params={"instrument": "ETH-USD", "quantity": 1.5},
    confidence=0.85,
    justification="Signal indicates upward momentum.",
)

# Evaluate the proposal through DIM (the sole execution gate)
verdict, reason = runtime.evaluate_proposal(
    proposal,
    raw_web_context={"current_price_eth_usd": 2450.0},
    allowed_agents=["trading_bot_01"],
)

if verdict == "ACCEPT":
    print(f"Authorized: {reason}")
    # Execute the side effect here
else:
    print(f"Rejected: {reason}")
    # Handle the rejection (log, escalate, retry with governor, etc.)
```

### Custom DIM Validator

Inject deterministic business-logic validators that run inside the kernel as part of the DIM evaluation:

```python
from dir_core import PolicyProposal
from typing import Any, Dict, Optional

def max_order_size_validator(
    proposal: PolicyProposal,
    ctx: Dict[str, Any],
    contract: Dict[str, Any],
) -> Optional[str]:
    if proposal.policy_kind not in ("BUY", "SELL"):
        return None
    quantity = float(proposal.params.get("quantity", 0))
    price = ctx.get("web", {}).get("current_price_eth_usd", 0)
    max_usd = contract.get("permissions", {}).get("max_order_size_usd", float("inf"))
    if quantity * price > max_usd:
        return f"ORDER_VALUE_EXCEEDED: {quantity * price:.2f} USD exceeds limit of {max_usd:.2f} USD"
    return None

verdict, reason = runtime.evaluate_proposal(
    proposal,
    raw_web_context={"current_price_eth_usd": 2450.0},
    custom_validators=[max_order_size_validator],
)
```

### Custom Storage Backend

Implement the `AgentRegistryStorage` protocol to plug in any persistence layer:

```python
from dir_core.storage import AgentRegistryStorage

class MyPostgresAgentStorage:
    def init_schema(self) -> None: ...
    def upsert_agent(self, agent_id, contract_json, priority,
                     status, agent_version, session_token) -> None: ...
    # Implement the remaining AgentRegistryStorage methods

from dir_core import AgentRegistry
registry = AgentRegistry(storage=MyPostgresAgentStorage())
```

The same protocol pattern applies to all other storage subsystems: `ContextStorage`, `DecisionAuditStorage`, `IdempotencyStorage`, `ResourceLockStorage`, `EscalationStorage`, `SagaStorage`, `IntentRetryStorage`, and `LifecycleStorage`. To replace the full bundle, pass a `StorageBundle` instance with your custom implementations to `DecisionRuntime`.

---

## Storage Backends Reference

| Backend factory | Persistence | External dependency | Recommended for |
|---|---|---|---|
| `memory_storage()` | In-process only | None | Unit tests, quick-start examples |
| `sqlite_storage(path)` | File-backed | None | Development, single-process workloads |
| Custom `StorageBundle` | Any | User-defined | PostgreSQL, Redis, cloud stores |

---

## Module Overview

| Module | Key exports | Description |
|---|---|---|
| `dir_core` | `DecisionRuntime`, `PolicyProposal`, `new_dfid` | Top-level package; re-exports all public symbols |
| `dir_core.runtime` | `DecisionRuntime` | Facade wiring `StorageBundle` to kernel services |
| `dir_core.dim` | `validate_proposal` | Deterministic proposal validation engine |
| `dir_core.agent_registry` | `AgentRegistry`, `HandshakeResult` | Agent registration and SemVer handshake |
| `dir_core.context_store` | `ContextStore` | Multi-layer session and state management |
| `dir_core.idempotency` | `IdempotencyGuard`, `idempotency_key` | SHA-256-keyed duplicate execution guard |
| `dir_core.escalation` | `EscalationManager`, `EscalationOutcome` | Token-bucket HITL escalation system |
| `dir_core.resource_lock` | `ResourceLockManager`, `LockResult` | Semantic resource reservation locks |
| `dir_core.jit` | `JITStateVerifier`, `verify_drift` | Pre-execution TOCTOU drift checks |
| `dir_core.event_bus` | `EventBus`, `create_event_bus` | In-memory event bus for EOAM topologies |
| `dir_core.pci` | `ProofChecker`, `compute_evidence_hash` | Proof-Carrying Intent verification (Topology C) |
| `dir_core.lifecycle` | `FlowStatus`, `transition` | DecisionFlow state machine |
| `dir_core.saga` | `SagaCompensation` | Structured multi-step rollback |
| `dir_core.intent_retry` | `IntentRetryGovernor`, `REASONING_EXHAUSTION` | Bounded retry governor for DIM and LLM loops |
| `dir_core.ledger` | `DecisionLedger` | Append-only PCI-signed audit ledger |
| `dir_core.wakeup` | `should_wake`, `WakeupPredicate` | EOAM Token-Burn prevention predicates |
| `dir_core.dfid` | `new_dfid`, `new_dfid_with_parent` | DFID generation and parent correlation |
| `dir_core.models` | `PolicyProposal`, `ExecutionIntent`, `ResponsibilityContract`, ... | All core domain Pydantic models |
| `dir_core.storage` | `StorageBundle`, `sqlite_storage`, `memory_storage`, protocols | Storage layer: protocols and built-in backends |

---

## Requirements

- Python 3.12 or later
- `pydantic >= 2.0`
- `structlog >= 24.1.0`
- `PyYAML >= 6.0`

Optional extras:

```bash
pip install "dir-runtime[postgres]"    # psycopg[binary] >= 3.1
pip install "dir-runtime[asyncpg]"     # asyncpg >= 0.29
pip install "dir-runtime[frameworks]"  # langchain-core (for LangChain adapter samples)
```

---

## License

Apache 2.0. See `LICENSE` for details.
