# Storage Schema (Data Model)

This document describes the canonical data model used by the Decision Intelligence Runtime (DIR). The tables defined here form the stateful backbone of Kernel Space, supporting the Agent Registry, Decision Flow lifecycle (`decision_flows`), Context Store, idempotency guards, resource locking, escalation, and audit.

The authoritative DDL is `src/dir_core/storage/schema.sql`. Depending on the backend (SQLite vs. PostgreSQL), concrete types may differ (for example `JSON` as `TEXT` in SQLite or `JSONB` in Postgres; timestamps as ISO-8601 `TEXT` in SQLite or `TIMESTAMPTZ` in Postgres). Application code must set `updated_at` fields on update — SQLite does not maintain them automatically.

## Entity-Relationship Diagram (ERD)

`decision_flows` is the lifecycle root: most runtime tables reference `dfid` and cascade on delete.

```mermaid
erDiagram
    agent_registry ||--o{ decision_flows : "agent_id"
    agent_registry ||--o| agent_state : "agent_id"
    agent_registry ||--o{ escalation_budget : "agent_id"
    agent_registry ||--o{ escalation_requests : "agent_id"
    agent_registry ||--o{ decision_feedback_trajectory : "agent_id"

    decision_flows ||--o{ decision_flows : "dfid_parent"
    decision_flows ||--o| flow_context : "dfid"
    decision_flows ||--o| saga_dirty_state : "dfid"
    decision_flows ||--o{ resource_locks : "dfid"
    decision_flows ||--o| intent_retry : "dfid"
    decision_flows ||--o{ escalation_requests : "dfid"
    decision_flows ||--o{ flow_transitions : "dfid"
    decision_flows ||--o{ decision_audit_events : "dfid"
    decision_flows ||--o{ decision_feedback_trajectory : "dfid"

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

    decision_flows {
        TEXT dfid PK
        TEXT root_dfid
        TEXT dfid_parent FK
        TEXT agent_id FK
        TEXT flow_type
        TEXT flow_version
        TEXT status
        TEXT created_by_type
        TEXT created_by_id
        INTEGER priority
        TIMESTAMP started_at
        TIMESTAMP completed_at
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    flow_context {
        TEXT dfid PK_FK
        JSON data
        INTEGER version
        TIMESTAMP updated_at
    }

    agent_state {
        TEXT agent_id PK_FK
        JSON data
        INTEGER version
        TIMESTAMP updated_at
    }

    decision_feedback_trajectory {
        INTEGER id PK
        TEXT agent_id FK
        TEXT dfid FK
        TEXT status
        TEXT reason
        REAL score
        TEXT source
        TIMESTAMP created_at
    }

    idempotency_cache {
        TEXT idempotency_key PK
        TEXT request_hash
        JSON result
        TIMESTAMP created_at
        TIMESTAMP expires_at
    }

    saga_dirty_state {
        TEXT dfid PK_FK
        TEXT failed_step
        JSON partial_state_json
        TIMESTAMP created_at
    }

    resource_locks {
        TEXT resource_id PK
        TEXT dfid FK
        REAL amount
        TIMESTAMP acquired_at
        TIMESTAMP expires_at
    }

    intent_retry {
        TEXT dfid PK_FK
        INTEGER rejection_count
        INTEGER max_retries
        TEXT retry_policy
        TIMESTAMP next_retry_at
        TIMESTAMP backoff_until
        TIMESTAMP updated_at
    }

    escalation_budget {
        INTEGER id PK
        TEXT agent_id FK
        TIMESTAMP created_at
    }

    escalation_requests {
        INTEGER id PK
        TEXT dfid FK
        TEXT root_dfid
        TEXT agent_id FK
        TEXT reason
        JSON context_json
        JSON proposal_json
        TEXT impact
        TEXT status
        TEXT human_decision
        TIMESTAMP created_at
        TIMESTAMP resolved_at
    }

    flow_transitions {
        INTEGER id PK
        TEXT dfid FK
        TEXT root_dfid
        TEXT from_status
        TEXT to_status
        TEXT correlation_id
        TEXT causation_id
        TIMESTAMP created_at
    }

    decision_audit_events {
        INTEGER id PK
        TEXT dfid FK
        TEXT root_dfid
        TEXT event_type
        TEXT severity
        TEXT correlation_id
        TEXT causation_id
        TEXT step_id
        TEXT state
        JSON detail_json
        TIMESTAMP created_at
    }
```

## Table Specifications

### Agent registry and decision flows

**`agent_registry`** (DIR §2.3)

Authoritative source of agent identity, responsibility contract, lifecycle status, and session token.

| Column | Description |
|--------|-------------|
| `agent_id` | Stable identifier supplied at handshake (PK). |
| `contract` | JSON responsibility contract (roles, policy types, limits). |
| `priority` | Registry ordering / precedence (default `0`). |
| `status` | `ACTIVE`, `SUSPENDED`, or `RETIRED`. |
| `agent_version` | Version string from handshake. |
| `session_token` | Opaque token for the current active session. |
| `suspension_reason` | Free-text reason when status is set by `AgentRegistry`. |
| `registered_at`, `updated_at` | Registration and last mutation timestamps. |

**`decision_flows`** (DIR §4.3)

Lifecycle root for every decision flow. Provides relational integrity and topology (`root_dfid`, `dfid_parent`).

| Column | Description |
|--------|-------------|
| `dfid` | Decision-Flow Identifier (PK, immutable). |
| `root_dfid` | Top-level flow id for lineage and tracing (not an FK — avoids bootstrap deadlocks). |
| `dfid_parent` | Immediate parent flow (delegation / escalation); FK to `decision_flows.dfid`. |
| `agent_id` | Owning agent; FK to `agent_registry.agent_id`. |
| `flow_type`, `flow_version` | Flow kind and schema version (defaults `DEFAULT`, `1.0`). |
| `status` | `CREATED`, `RUNNING`, `WAITING_ESCALATION`, `COMPLETED`, `FAILED`, `CANCELLED`, `COMPENSATING`, `COMPENSATED`. |
| `created_by_type`, `created_by_id` | Optional provenance of flow creation. |
| `priority` | Flow priority (default `0`). |
| `started_at`, `completed_at` | Execution window. |
| `created_at`, `updated_at` | Row lifecycle timestamps. |

Constraint: if `dfid_parent` is null, `root_dfid` must equal `dfid`; otherwise `root_dfid` must be non-empty.

### Context store

**`flow_context`** (DIR §8 — per-flow session)

Transient, DFID-scoped context written by the Context Compiler before the agent receives the flow. Typically read-once by the agent.

| Column | Description |
|--------|-------------|
| `dfid` | PK and FK to `decision_flows.dfid` (cascade delete). |
| `data` | JSON compiled context snapshot. |
| `version` | Optimistic-lock version (default `1`). |
| `updated_at` | Last write time. |

**`agent_state`** (DIR §8 — persistent agent state)

Long-lived, agent-scoped state across flows (running averages, thresholds, and similar).

| Column | Description |
|--------|-------------|
| `agent_id` | PK and FK to `agent_registry.agent_id` (cascade delete). |
| `data` | JSON payload. |
| `version` | Monotonically incremented on write for optimistic locking. |
| `updated_at` | Last write time. |

**`decision_feedback_trajectory`** (DIR §8 — epistemic trajectory)

Historical DIM outcomes per agent/flow for long-term memory (accepted, rejected, escalate).

| Column | Description |
|--------|-------------|
| `id` | Surrogate PK (auto-increment). |
| `agent_id`, `dfid` | FKs to registry and decision flow. |
| `status` | Outcome label (for example Accepted, Rejected, Escalate). |
| `reason` | Optional explanation. |
| `score` | Optional numeric quality score. |
| `source` | Origin: `Human`, `Monitor`, `KERNEL` (default `KERNEL`). |
| `created_at` | Event time. |

### Safety and integrity

**`idempotency_cache`** (DIR §7)

Prevents duplicate execution of the same logical operation.

| Column | Description |
|--------|-------------|
| `idempotency_key` | Application-defined token (PK). |
| `request_hash` | Hash of request payload (TOCTOU protection). |
| `result` | Cached JSON outcome for replays. |
| `created_at`, `expires_at` | Insert time and TTL. |

**`resource_locks`** (DIR §6.2)

Exclusive resource reservations held by a flow.

| Column | Description |
|--------|-------------|
| `resource_id` | Locked resource identifier (PK). |
| `dfid` | Holding flow; FK to `decision_flows`. |
| `amount` | Reserved quantity (default `0`). |
| `acquired_at`, `expires_at` | Lock time and optional expiry (deadlock prevention). |

**`intent_retry`** (DIR §6.2)

Governor for rejection/re-submit loops (hallucination-loop protection).

| Column | Description |
|--------|-------------|
| `dfid` | PK and FK to `decision_flows`. |
| `rejection_count` | Number of DIM rejections for this flow. |
| `max_retries` | Cap (default `3`). |
| `retry_policy` | Policy name (default `EXPONENTIAL_BACKOFF`). |
| `next_retry_at`, `backoff_until` | Scheduled retry windows. |
| `updated_at` | Last mutation. |

**`saga_dirty_state`** (DIR §7)

Partial saga state when a multi-step flow fails mid-flight (compensation / sweep).

| Column | Description |
|--------|-------------|
| `dfid` | PK and FK to `decision_flows`. |
| `failed_step` | Step that failed. |
| `partial_state_json` | JSON partial state. |
| `created_at` | When dirty state was recorded. |

### Human-in-the-loop and audit

**`escalation_budget`** (DIR §9)

Append-only log of escalation tokens consumed per agent (rolling rate limits).

| Column | Description |
|--------|-------------|
| `id` | Surrogate PK. |
| `agent_id` | FK to `agent_registry`. |
| `created_at` | Consumption time. |

**`escalation_requests`** (DIR §9)

One row per escalation request. Status: `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`.

| Column | Description |
|--------|-------------|
| `id` | Surrogate PK (multiple rows per `dfid` allowed). |
| `dfid`, `root_dfid` | Flow identifiers; `dfid` FK to `decision_flows`. |
| `agent_id` | Requesting agent. |
| `reason`, `impact` | Human-readable summary. |
| `context_json`, `proposal_json` | Serialized context and proposal. |
| `status` | Workflow state. |
| `human_decision` | Operator outcome text. |
| `created_at`, `resolved_at` | Open and close times. |

**`flow_transitions`** (DIR §4.3)

Append-only lifecycle transition log per flow.

| Column | Description |
|--------|-------------|
| `id` | Surrogate PK. |
| `dfid`, `root_dfid` | Flow identifiers; `dfid` FK to `decision_flows`. |
| `from_status`, `to_status` | State change. |
| `correlation_id`, `causation_id` | Distributed tracing hooks. |
| `created_at` | Transition time. |

**`decision_audit_events`** (observability)

DFID-scoped audit rows for compliance and debugging. Exposed via `DecisionAuditStorage`.

| Column | Description |
|--------|-------------|
| `id` | Surrogate PK. |
| `dfid`, `root_dfid` | Flow identifiers; `dfid` FK to `decision_flows`. |
| `event_type` | Event name (for example `AGENT_DECISION`, `SIMULATION_START`). |
| `severity` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default `INFO`). |
| `correlation_id`, `causation_id` | Tracing hooks. |
| `step_id`, `state` | Optional pipeline position labels. |
| `detail_json` | Arbitrary JSON payload. |
| `created_at` | Event time. |

## Indexes

The DDL defines supporting indexes on status, foreign keys, time columns, and audit dimensions (`event_type`, `severity`). See `schema.sql` for the full list.

## Custom backends

1. Apply this DDL (or equivalent) in your database.
2. Implement the protocols in `dir_core/storage/base.py`.
3. Pass instances via the `storage=` keyword on manager classes.

The built-in SQLite backend in `dir_core/storage/sqlite.py` applies `schema.sql` automatically on first use.
