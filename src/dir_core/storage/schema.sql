-- =============================================================================
-- DIR Repository Schema — Canonical Data Model
-- Decision Intelligence Runtime (DIR)
-- =============================================================================
--
-- This file is the authoritative DDL for all tables required by DIR.
--
-- PURPOSE
--   Read this file to understand the data model before implementing a custom
--   storage backend.  Create these tables in your target database (PostgreSQL,
--   MySQL, SQL Server, …) and implement the Python Protocols defined in
--   dir_core/storage/base.py to wire DIR into your infrastructure.
--
-- SQLITE REFERENCE IMPLEMENTATION
--   dir_core/storage/sqlite.py ships a ready-to-use SQLite backend.
--   It applies this file verbatim on first use.  You do NOT need to run this
--   file manually when using the built-in SQLite backend.
--
-- CUSTOM BACKEND WORKFLOW
--   1. Apply this DDL (or an equivalent) to your database.
--   2. Implement each Protocol from dir_core/storage/base.py.
--   3. Pass your instances via the storage= kwarg of each manager class.
--   See docs/dir_repository_example.py for a fully annotated example.
--
-- TIMESTAMPS NOTE
--   - updated_at fields are APPLICATION-MANAGED. SQLite does not update them
--     automatically on row modification.
--
-- COLUMN TYPE NOTES
--   - JSON     : stored as TEXT in SQLite; use native JSON/JSONB in Postgres.
--   - TIMESTAMP: stored as TEXT (ISO-8601) in SQLite; use TIMESTAMPTZ in Postgres.
--   - REAL     : 64-bit float.  Use NUMERIC / DECIMAL where precision matters.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- DIR §2.3 — Agent Registry
--
-- One row per registered agent.  The registry is the authoritative source of
-- agent identity, responsibility contract, lifecycle status, and session token.
--
-- Key columns:
--   agent_id         Stable identifier supplied by the agent at handshake.
--   contract         JSON responsibility contract (roles, policy types, limits).
--   status           Lifecycle state: ACTIVE | SUSPENDED | RETIRED.
--   suspension_reason  Free-text reason written by AgentRegistry.set_agent_status.
--   session_token    Opaque token scoped to the current active session.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_registry (
    agent_id          TEXT PRIMARY KEY,
    contract          JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(contract)),
    priority          INTEGER   NOT NULL DEFAULT 0,
    status            TEXT      NOT NULL DEFAULT 'ACTIVE',
    agent_version     TEXT,
    session_token     TEXT,
    suspension_reason TEXT,
    registered_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_registry_status
ON agent_registry(status);


-- -----------------------------------------------------------------------------
-- DIR §4.3 — Decision Flows (Lifecycle root)
--
-- Main table for tracing execution contexts. Provides relational integrity for
-- all runtime operations and topological flow mapping.
--
-- Key columns:
--   dfid            Decision-Flow Identifier — immutable primary key.
--   root_dfid       Top-level flow identifier. NOTE: Not a Foreign Key to avoid 
--                   bootstrapping deadlocks. Used for lineage, traversal 
--                   optimization, analytics and distributed tracing.
--   dfid_parent     Immediate parent flow (for Delegation/Escalation).
--   status          Lifecycle state (CREATED | RUNNING | FAILED | COMPLETED ...).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_flows (
    dfid            TEXT PRIMARY KEY,
    root_dfid       TEXT NOT NULL,
    dfid_parent     TEXT,
    agent_id        TEXT NOT NULL,

    flow_type       TEXT NOT NULL DEFAULT 'DEFAULT',
    flow_version    TEXT NOT NULL DEFAULT '1.0',

    status          TEXT NOT NULL DEFAULT 'CREATED',

    created_by_type TEXT,
    created_by_id   TEXT,

    priority        INTEGER NOT NULL DEFAULT 0,

    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid_parent)
        REFERENCES decision_flows(dfid),

    FOREIGN KEY (agent_id)
        REFERENCES agent_registry(agent_id),

    CHECK (
        status IN (
            'CREATED',
            'RUNNING',
            'WAITING_ESCALATION',
            'COMPLETED',
            'FAILED',
            'CANCELLED',
            'COMPENSATING',
            'COMPENSATED'
        )
    ),
    -- DIR §4.3 — Topology consistency
    CHECK (
        (dfid_parent IS NULL AND root_dfid = dfid) OR
        (dfid_parent IS NOT NULL AND root_dfid != '')
    )
);

CREATE INDEX IF NOT EXISTS idx_decision_flows_root_dfid ON decision_flows(root_dfid);
CREATE INDEX IF NOT EXISTS idx_decision_flows_parent ON decision_flows(dfid_parent);
CREATE INDEX IF NOT EXISTS idx_decision_flows_agent_id ON decision_flows(agent_id);
CREATE INDEX IF NOT EXISTS idx_decision_flows_status ON decision_flows(status);
CREATE INDEX IF NOT EXISTS idx_decision_flows_created_at ON decision_flows(created_at);


-- -----------------------------------------------------------------------------
-- DIR §8 — Context Store: per-flow session data
--
-- Transient, dfid-scoped context written by the Context Compiler before the
-- agent receives the decision flow. Consumed (read-once) by the agent and
-- then discarded or archived.
--
-- Key columns:
--   dfid  Decision-Flow Identifier.
--   data  JSON snapshot of the compiled context (market state, permissions, …).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flow_context (
    dfid        TEXT PRIMARY KEY,
    data          JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(data)),
    version     INTEGER   NOT NULL DEFAULT 1,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid)
        REFERENCES decision_flows(dfid)
        ON DELETE CASCADE
);


-- -----------------------------------------------------------------------------
-- DIR §8 — Context Store: persistent agent state
--
-- Long-lived, agent-scoped state that survives across individual decision flows
-- (e.g., running averages, learned thresholds, last-seen values).
--
-- Key columns:
--   agent_id  References agent_registry.agent_id.
--   version   Monotonically incremented on every write for optimistic locking.
--   data      Arbitrary JSON payload managed by the agent / Context Compiler.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_state (
    agent_id    TEXT PRIMARY KEY,
    data          JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(data)),
    version     INTEGER   NOT NULL DEFAULT 1,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (agent_id)
        REFERENCES agent_registry(agent_id)
        ON DELETE CASCADE
);


-- -----------------------------------------------------------------------------
-- DIR §8 — Context Store: decision feedback (Epistemic Trajectory)
--
-- Agent memory trajectory for Epistemic Longevity (Long-Term Memory).
-- Stores feedback outcomes from DIM over historical decisions to prevent amnesia.
--
-- Key columns:
--   agent_id  References agent_registry.agent_id.
--   dfid      Specific execution instance.
--   status    Outcome status (Accepted, Rejected, Escalate).
--   score     Optional numerical evaluation of quality.
--   source    Origin (Human, Monitor, Kernel).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_feedback_trajectory (
    id          INTEGER   PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT      NOT NULL,
    dfid        TEXT      NOT NULL,
    status      TEXT      NOT NULL,
    reason      TEXT,
    score       REAL,
    source      TEXT      NOT NULL DEFAULT 'KERNEL',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (agent_id) REFERENCES agent_registry(agent_id) ON DELETE CASCADE,
    FOREIGN KEY (dfid) REFERENCES decision_flows(dfid) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_decision_feedback_agent ON decision_feedback_trajectory(agent_id);


-- -----------------------------------------------------------------------------
-- DIR §7 — Idempotency Cache
--
-- Guards against duplicate execution of the same logical operation.
-- The key is an application-defined idempotency token.
-- Result is stored so a replay returns the cached outcome without re-running.
-- Includes request_hash for protection against TOCTOU manipulation.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS idempotency_cache (
    idempotency_key TEXT PRIMARY KEY,
    request_hash    TEXT      NOT NULL,
    result          JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(result)),

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_cache_expires_at
ON idempotency_cache(expires_at);


-- -----------------------------------------------------------------------------
-- DIR §7 — Saga / Compensation: dirty-state log
--
-- When a multi-step saga fails mid-flight, the partial state is written here
-- so a compensating transaction can clean it up later.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saga_dirty_state (
    dfid                TEXT PRIMARY KEY,
    failed_step         TEXT      NOT NULL DEFAULT '',
    partial_state_json  JSON      NOT NULL DEFAULT '{}',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid)
        REFERENCES decision_flows(dfid)
        ON DELETE CASCADE
);


-- -----------------------------------------------------------------------------
-- DIR §6.2 — Resource Lock Manager
--
-- Tracks exclusive resource reservations held by a decision flow.
-- Automatically expires via expires_at to prevent permanent deadlocks.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resource_locks (
    resource_id   TEXT PRIMARY KEY,
    dfid          TEXT      NOT NULL,
    amount        REAL      NOT NULL DEFAULT 0,
    acquired_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    TIMESTAMP,

    FOREIGN KEY (dfid)
        REFERENCES decision_flows(dfid)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resource_locks_dfid ON resource_locks(dfid);
CREATE INDEX IF NOT EXISTS idx_resource_locks_expires_at ON resource_locks(expires_at);


-- -----------------------------------------------------------------------------
-- DIR §6.2 — Intent Retry Governor
--
-- Prevents Hallucination Loops by enforcing a max retry policy and tracking
-- rejections for subsequent executions context.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intent_retry (
    dfid               TEXT PRIMARY KEY,
    rejection_count    INTEGER   NOT NULL DEFAULT 0,
    max_retries        INTEGER   NOT NULL DEFAULT 3,
    retry_policy       TEXT      NOT NULL DEFAULT 'EXPONENTIAL_BACKOFF',
    next_retry_at      TIMESTAMP,
    backoff_until      TIMESTAMP,
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid)
        REFERENCES decision_flows(dfid)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_intent_retry_next_retry_at ON intent_retry(next_retry_at);


-- -----------------------------------------------------------------------------
-- DIR §9 — Escalation Manager: rate-limit budget
--
-- Append-only log of escalation tokens consumed by an agent within a rolling
-- time window to enforce per-agent escalation rate limits.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalation_budget (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT      NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (agent_id)
        REFERENCES agent_registry(agent_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_escalation_budget_agent_id ON escalation_budget(agent_id);
CREATE INDEX IF NOT EXISTS idx_escalation_budget_created_at ON escalation_budget(created_at);


-- -----------------------------------------------------------------------------
-- DIR §9 — Escalation Manager: pending and resolved requests
--
-- One row per escalation request. Handles transitions: 
-- PENDING → APPROVED | REJECTED | RESOLVED.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalation_requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dfid             TEXT      NOT NULL,
    root_dfid        TEXT      NOT NULL,
    agent_id         TEXT      NOT NULL,

    reason           TEXT      NOT NULL DEFAULT '',
    context_json     JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(context_json)),
    proposal_json    JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(proposal_json)),
    impact           TEXT      NOT NULL DEFAULT '',
    status           TEXT      NOT NULL DEFAULT 'PENDING',
    human_decision   TEXT,

    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at      TIMESTAMP,

    FOREIGN KEY (dfid) REFERENCES decision_flows(dfid) ON DELETE CASCADE,
    
    FOREIGN KEY (agent_id) REFERENCES agent_registry(agent_id),

    CHECK (
        status IN (
            'PENDING',
            'APPROVED',
            'REJECTED',
            'CANCELLED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_escalation_requests_dfid ON escalation_requests(dfid);
CREATE INDEX IF NOT EXISTS idx_escalation_requests_root_dfid ON escalation_requests(root_dfid);
CREATE INDEX IF NOT EXISTS idx_escalation_requests_agent_id ON escalation_requests(agent_id);
CREATE INDEX IF NOT EXISTS idx_escalation_requests_status ON escalation_requests(status);


-- -----------------------------------------------------------------------------
-- DIR §4.3 — Lifecycle: flow transition log
--
-- Append-only audit trail of every state transition for every decision flow.
-- Used for observability, debugging, and post-hoc compliance audits.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flow_transitions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dfid          TEXT      NOT NULL,
    root_dfid     TEXT      NOT NULL,
    from_status   TEXT,
    to_status     TEXT      NOT NULL,
    correlation_id TEXT,
    causation_id   TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid) REFERENCES decision_flows(dfid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_flow_transitions_dfid ON flow_transitions(dfid);
CREATE INDEX IF NOT EXISTS idx_flow_transitions_root_dfid ON flow_transitions(root_dfid);
CREATE INDEX IF NOT EXISTS idx_flow_transitions_created_at ON flow_transitions(created_at);


-- -----------------------------------------------------------------------------
-- DIR §5.4 — Decision Ledger (Topology C / DL+PCI)
--
-- Append-only store of verified Proof-Carrying Intents. Only DIM-approved PCIs
-- are persisted. One row per decision flow (idempotent replay via UNIQUE dfid).
--
-- Key columns:
--   dfid            Decision-Flow Identifier (immutable, one verified PCI per flow).
--   intent_payload  Full domain proposal bound in the PCI artifact.
--   context_ref     ContextSnapshotID hash used during evidence_hash derivation.
--   evidence_hash   SHA256(DFID || Context_Hash || Contract_Hash || Proposal_Params).
--   signature       Cryptographic signature binding PCI to agent identity.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_ledger_entries (
    id              INTEGER   PRIMARY KEY AUTOINCREMENT,
    dfid            TEXT      NOT NULL UNIQUE,
    root_dfid       TEXT      NOT NULL,
    agent_id        TEXT      NOT NULL,

    intent_payload  JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(intent_payload)),
    context_ref     TEXT      NOT NULL,
    evidence_hash   TEXT      NOT NULL,
    signature       TEXT      NOT NULL DEFAULT '',

    committed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid) REFERENCES decision_flows(dfid) ON DELETE CASCADE,
    FOREIGN KEY (agent_id) REFERENCES agent_registry(agent_id)
);

CREATE INDEX IF NOT EXISTS idx_decision_ledger_entries_dfid ON decision_ledger_entries(dfid);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_entries_agent_id ON decision_ledger_entries(agent_id);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_entries_committed_at ON decision_ledger_entries(committed_at);


-- -----------------------------------------------------------------------------
-- Observability — append-only decision audit events (core data model)
--
-- DFID-scoped audit rows for compliance and debugging. Exposed as 
-- DecisionAuditStorage.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_audit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dfid            TEXT      NOT NULL,
    root_dfid       TEXT      NOT NULL,

    event_type      TEXT      NOT NULL,
    severity        TEXT      NOT NULL DEFAULT 'INFO',
    correlation_id  TEXT,
    causation_id    TEXT,

    step_id         TEXT      NOT NULL DEFAULT '',
    state           TEXT      NOT NULL DEFAULT '',

    detail_json     JSON      NOT NULL DEFAULT '{}' CHECK(json_valid(detail_json)),

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (dfid) REFERENCES decision_flows(dfid) ON DELETE CASCADE,
    

    CHECK (
        severity IN (
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_decision_audit_events_dfid ON decision_audit_events(dfid);
CREATE INDEX IF NOT EXISTS idx_decision_audit_events_root_dfid ON decision_audit_events(root_dfid);
CREATE INDEX IF NOT EXISTS idx_decision_audit_events_event_type ON decision_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_decision_audit_events_created_at ON decision_audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_decision_audit_events_severity ON decision_audit_events(severity);
