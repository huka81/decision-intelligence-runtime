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
-- COLUMN TYPE NOTES
--   - JSON     : stored as TEXT in SQLite; use native JSON/JSONB in Postgres.
--   - TIMESTAMP: stored as TEXT (ISO-8601) in SQLite; use TIMESTAMPTZ in Postgres.
--   - REAL     : 64-bit float.  Use NUMERIC / DECIMAL where precision matters.
-- =============================================================================


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
    agent_id          TEXT      PRIMARY KEY,
    contract          JSON      NOT NULL DEFAULT '{}',
    priority          INTEGER   NOT NULL DEFAULT 0,
    status            TEXT      NOT NULL DEFAULT 'ACTIVE',
    agent_version     TEXT,
    session_token     TEXT,
    suspension_reason TEXT,
    registered_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §8 — Context Store: per-flow session data
--
-- Transient, dfid-scoped context written by the Context Compiler before the
-- agent receives the decision flow.  Consumed (read-once) by the agent and
-- then discarded or archived.
--
-- Key columns:
--   dfid  Decision-Flow Identifier — immutable primary key of every flow.
--   data  JSON snapshot of the compiled context (market state, permissions, …).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS context_session (
    dfid       TEXT      PRIMARY KEY,
    data       JSON      NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §8 — Context Store: persistent agent state
--
-- Long-lived, agent-scoped state that survives across individual decision flows
-- (e.g., running averages, learned thresholds, last-seen values).
--
-- Key columns:
--   agent_id  References agent_registry.agent_id (soft FK).
--   version   Monotonically incremented on every write; used for optimistic locking.
--   data      Arbitrary JSON payload managed by the agent / Context Compiler.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS context_state (
    agent_id   TEXT      PRIMARY KEY,
    data       JSON      NOT NULL DEFAULT '{}',
    version    INTEGER   NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §7 — Idempotency Cache
--
-- Guards against duplicate execution of the same logical operation.
-- The key is an application-defined idempotency token (e.g., hash of inputs).
-- Result is stored so a replay returns the cached outcome without re-running.
--
-- Key columns:
--   key     Caller-supplied idempotency key (SHA-256 of request body, etc.).
--   result  JSON result that was produced on the first execution.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS idempotency_cache (
    key        TEXT      PRIMARY KEY,
    result     JSON      NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §7 — Saga / Compensation: dirty-state log
--
-- When a multi-step saga fails mid-flight, the partial state is written here
-- so a compensating transaction can clean it up on the next startup or via
-- a background sweep.
--
-- Key columns:
--   dfid               Identifies the failed decision flow.
--   failed_step        Name of the step that failed (for targeted compensation).
--   partial_state_json JSON snapshot of state at the point of failure.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saga_dirty_state (
    dfid               TEXT      PRIMARY KEY,
    failed_step        TEXT      NOT NULL DEFAULT '',
    partial_state_json TEXT      NOT NULL DEFAULT '{}',
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §6.2 — Resource Lock Manager
--
-- Tracks exclusive resource reservations held by a decision flow.
-- A (dfid, resource_id) pair is inserted atomically when a lock is granted
-- and deleted when the flow completes or rolls back.
--
-- Key columns:
--   dfid         Decision flow that holds the lock.
--   resource_id  Logical resource name (e.g., "portfolio:BTC", "credit_limit:42").
--   amount       Reserved quantity (units are domain-specific).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resource_locks (
    dfid        TEXT      NOT NULL,
    resource_id TEXT      NOT NULL,
    amount      REAL      NOT NULL DEFAULT 0,
    acquired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dfid, resource_id)
);


-- -----------------------------------------------------------------------------
-- DIR §6.2 — Intent Retry Governor
--
-- Counts how many times a decision flow has been rejected and re-submitted.
-- The governor suspends or drops the flow once the rejection_count exceeds the
-- configured threshold, preventing infinite retry loops.
--
-- Key columns:
--   dfid             Decision flow under retry governance.
--   rejection_count  Number of consecutive rejections so far.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intent_retry (
    dfid            TEXT      PRIMARY KEY,
    rejection_count INTEGER   NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §9 — Escalation Manager: rate-limit budget
--
-- Append-only log of escalation tokens consumed by an agent within a rolling
-- time window.  The EscalationManager counts rows in this table to enforce the
-- per-agent escalation rate limit before accepting a new escalation request.
--
-- Key columns:
--   agent_id    References the agent that triggered the escalation.
--   created_at  Timestamp used for the rolling-window count query.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalation_budget (
    id         INTEGER   PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT      NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- -----------------------------------------------------------------------------
-- DIR §9 — Escalation Manager: pending and resolved requests
--
-- One row per escalation request.  Status transitions:
--   PENDING → RESOLVED (human approves or rejects via resolve_request).
--
-- Key columns:
--   dfid           Decision flow that triggered the escalation.
--   reason         Why the agent could not decide autonomously.
--   context_json   Serialised context snapshot at escalation time.
--   proposal_json  Agent's best-effort proposal (may be empty).
--   impact         Human-readable impact assessment supplied by the agent.
--   status         PENDING | RESOLVED.
--   human_decision Free-text or structured decision written by the human reviewer.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalation_requests (
    dfid           TEXT      PRIMARY KEY,
    agent_id       TEXT      NOT NULL,
    reason         TEXT      NOT NULL DEFAULT '',
    context_json   TEXT      NOT NULL DEFAULT '{}',
    proposal_json  TEXT      NOT NULL DEFAULT '{}',
    impact         TEXT      NOT NULL DEFAULT '',
    status         TEXT      NOT NULL DEFAULT 'PENDING',
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at    TIMESTAMP,
    human_decision TEXT
);


-- -----------------------------------------------------------------------------
-- DIR §4.3 — Lifecycle: flow transition log
--
-- Append-only audit trail of every state transition for every decision flow.
-- Used for observability, debugging, and post-hoc compliance audits.
--
-- Key columns:
--   dfid         Decision flow whose status changed.
--   from_status  Previous lifecycle state (NULL on initial CREATED transition).
--   to_status    New lifecycle state (CREATED | RUNNING | COMPLETED | FAILED | …).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flow_transitions (
    id          INTEGER   PRIMARY KEY AUTOINCREMENT,
    dfid        TEXT      NOT NULL,
    from_status TEXT,
    to_status   TEXT      NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
