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
