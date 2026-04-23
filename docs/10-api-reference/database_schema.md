# Storage Schema (Data Model)

This document describes the canonical data model (Schema) used by the Decision Intelligence Runtime (DIR). The tables defined here form the stateful backbone of the Kernel Space, supporting features like Agent Registry, DecisionFlow ID (DFID) tracking, Context Storage, Idempotency Guards, and Escalation limits.

## Entity-Relationship Diagram (ERD)

The following diagram illustrates the core tables and their relationships. 

```mermaid
erDiagram
    agent_registry ||--o{ context_state : "agent_id"
    agent_registry ||--o{ escalation_budget : "agent_id"
    agent_registry ||--o{ escalation_requests : "agent_id"

    context_session ||--o| saga_dirty_state : "dfid"
    context_session ||--o{ resource_locks : "dfid"
    context_session ||--o| intent_retry : "dfid"
    context_session ||--o| escalation_requests : "dfid"
    context_session ||--o{ flow_transitions : "dfid"
    context_session ||--o{ decision_audit_events : "dfid"

    agent_registry {
        TEXT agent_id PK
        JSON contract
        INTEGER priority
        TEXT status
        TEXT agent_version
        TEXT session_token
        TEXT suspension_reason
        TIMESTAMP registered_at
        TIMESTAMP updated_at
    }

    context_session {
        TEXT dfid PK
        JSON data
        TIMESTAMP updated_at
    }

    context_state {
        TEXT agent_id PK
        JSON data
        INTEGER version
        TIMESTAMP updated_at
    }

    idempotency_cache {
        TEXT key PK
        JSON result
        TIMESTAMP created_at
    }

    saga_dirty_state {
        TEXT dfid PK
        TEXT failed_step
        TEXT partial_state_json
        TIMESTAMP created_at
    }

    resource_locks {
        TEXT dfid PK
        TEXT resource_id PK
        REAL amount
        TIMESTAMP acquired_at
    }

    intent_retry {
        TEXT dfid PK
        INTEGER rejection_count
        TIMESTAMP updated_at
    }

    escalation_budget {
        INTEGER id PK
        TEXT agent_id
        TIMESTAMP created_at
    }

    escalation_requests {
        TEXT dfid PK
        TEXT agent_id
        TEXT reason
        TEXT context_json
        TEXT proposal_json
        TEXT impact
        TEXT status
        TIMESTAMP created_at
        TIMESTAMP resolved_at
        TEXT human_decision
    }

    flow_transitions {
        INTEGER id PK
        TEXT dfid
        TEXT from_status
        TEXT to_status
        TIMESTAMP created_at
    }

    decision_audit_events {
        INTEGER id PK
        TEXT dfid
        TEXT event
        TEXT timestamp
        TEXT step_id
        TEXT state
        JSON detail_json
    }
```

## Table Specifications

The authoritative DDL can be found in `src/dir_core/storage/schema.sql`. Depending on the backend (e.g., SQLite vs. PostgreSQL), the exact types might vary (e.g. `JSON` mapping to `TEXT` in SQLite or `JSONB` in Postgres).

### Core Components

**`agent_registry`**
Authoritative source of agent identity, capability contracts, lifecycle status, and session token.
- **`agent_id`**: Stable identifier supplied by the agent at handshake.
- **`contract`**: JSON responsibility contract (roles, policy types, limits).
- **`status`**: Lifecycle state (`ACTIVE`, `SUSPENDED`, `RETIRED`).

**`context_session`**
Transient, DFID-scoped context written by the Context Compiler before the agent receives the decision flow. Consumed (read-once) by the agent.

**`context_state`**
Long-lived, agent-scoped state that survives across individual decision flows (e.g., running averages, learned thresholds).
- **`version`**: Monotonically incremented on every write, used for optimistic locking.

### Safety & Integrity Mechanisms

**`idempotency_cache`**
Guards against duplicate execution. The caller supplies a unique idempotency key (e.g. SHA-256 of the request). The result is cached to prevent re-execution.

**`resource_locks`**
Tracks exclusive resource reservations held by a decision flow (`dfid`, `resource_id`). Inserted atomically when a lock is granted and deleted upon flow completion or rollback.

**`intent_retry`**
Governor table that counts how many times a decision flow has been rejected and re-submitted to prevent infinite LLM retry loops.

**`saga_dirty_state`**
When a multi-step saga fails mid-flight, partial state is persisted here to allow compensating transactions or background sweeps to clean it up.

### Human-in-the-Loop & Audit

**`escalation_budget`**
Append-only log of escalation tokens consumed by an agent. Used by the EscalationManager to enforce per-agent rate limits over a rolling time window.

**`escalation_requests`**
One row per escalation request traversing the `PENDING` → `RESOLVED` states. Contains the agent's proposal, context, and human decision.

**`flow_transitions`**
Append-only audit trail of every lifecycle state transition for a decision flow (`CREATED` → `RUNNING` → `COMPLETED` / `FAILED`).

**`decision_audit_events`**
DFID-scoped audit rows tracking detailed steps, states, and operations for compliance and debugging. Exposed via `DecisionAuditStorage`.
