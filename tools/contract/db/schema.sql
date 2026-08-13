PRAGMA foreign_keys = ON;

-- Contract Studio — dedicated SQLite schema (not dir_core)

CREATE TABLE IF NOT EXISTS contract_sessions (
  id                  TEXT PRIMARY KEY,
  agent_id            TEXT,
  title               TEXT NOT NULL,
  preset              TEXT,
  status              TEXT NOT NULL DEFAULT 'drafting'
                        CHECK (status IN ('drafting', 'ready', 'exported', 'abandoned')),
  current_revision_id TEXT,
  llm_provider        TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id          TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL REFERENCES contract_sessions(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content     TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_revisions (
  id                TEXT PRIMARY KEY,
  session_id        TEXT NOT NULL REFERENCES contract_sessions(id) ON DELETE CASCADE,
  revision_no       INTEGER NOT NULL,
  contract_json     TEXT NOT NULL CHECK (json_valid(contract_json)),
  contract_yaml     TEXT NOT NULL,
  validation_ok     INTEGER NOT NULL DEFAULT 0,
  validation_errors TEXT,
  source_message_id TEXT REFERENCES chat_messages(id),
  change_summary    TEXT,
  created_at        TEXT NOT NULL,
  UNIQUE (session_id, revision_no)
);

CREATE TABLE IF NOT EXISTS contract_exports (
  id           TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL REFERENCES contract_sessions(id) ON DELETE CASCADE,
  revision_id  TEXT NOT NULL REFERENCES contract_revisions(id),
  emit_mode    TEXT NOT NULL CHECK (emit_mode IN ('registry', 'sample', 'both')),
  output_paths TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_revisions_session ON contract_revisions(session_id, revision_no);

CREATE TABLE IF NOT EXISTS governance_context_snapshots (
  id           TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL UNIQUE REFERENCES contract_sessions(id) ON DELETE CASCADE,
  pack_id      TEXT NOT NULL,
  pack_version TEXT NOT NULL,
  context_json TEXT NOT NULL CHECK (json_valid(context_json)),
  context_hash TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revision_governance_assessments (
  id                TEXT PRIMARY KEY,
  revision_id       TEXT NOT NULL UNIQUE REFERENCES contract_revisions(id) ON DELETE CASCADE,
  analysis_json     TEXT CHECK (analysis_json IS NULL OR json_valid(analysis_json)),
  report_json       TEXT NOT NULL CHECK (json_valid(report_json)),
  warnings_json     TEXT NOT NULL CHECK (json_valid(warnings_json)),
  llm_response_json TEXT CHECK (llm_response_json IS NULL OR json_valid(llm_response_json)),
  created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_governance_session ON governance_context_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_assessment_revision ON revision_governance_assessments(revision_id);
