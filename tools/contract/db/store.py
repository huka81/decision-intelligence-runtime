"""SQLite store for Contract Studio sessions, chat, revisions, and exports."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "contract_studio.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class SessionRow:
    id: str
    agent_id: Optional[str]
    title: str
    preset: Optional[str]
    status: str
    current_revision_id: Optional[str]
    llm_provider: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class MessageRow:
    id: str
    session_id: str
    role: str
    content: str
    created_at: str


@dataclass
class RevisionRow:
    id: str
    session_id: str
    revision_no: int
    contract_json: str
    contract_yaml: str
    validation_ok: bool
    validation_errors: Optional[str]
    source_message_id: Optional[str]
    change_summary: Optional[str]
    created_at: str


@dataclass
class ExportRow:
    id: str
    session_id: str
    revision_id: str
    emit_mode: str
    output_paths: str
    created_at: str


@dataclass
class GovernanceSnapshotRow:
    id: str
    session_id: str
    pack_id: str
    pack_version: str
    context_json: str
    context_hash: str
    created_at: str


@dataclass
class GovernanceAssessmentRow:
    id: str
    revision_id: str
    analysis_json: Optional[str]
    report_json: str
    warnings_json: str
    llm_response_json: Optional[str]
    created_at: str


class ContractStudioStore:
    """Persistence layer for Contract Studio."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = Path(db_path or _DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(ddl)
            conn.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Apply additive migrations for existing Studio databases."""
        with self._connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "governance_context_snapshots" not in tables:
                conn.executescript(
                    """
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
                    """
                )
                conn.commit()

    def create_session(
        self,
        *,
        title: str,
        preset: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> SessionRow:
        session_id = _new_id()
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_sessions
                  (id, agent_id, title, preset, status, current_revision_id,
                   llm_provider, created_at, updated_at)
                VALUES (?, NULL, ?, ?, 'drafting', NULL, ?, ?, ?)
                """,
                (session_id, title, preset, llm_provider, now, now),
            )
            conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionRow:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contract_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session not found: {session_id}")
        return self._session_from_row(row)

    def list_sessions(self) -> List[SessionRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contract_sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [self._session_from_row(r) for r in rows]

    def update_session(
        self,
        session_id: str,
        *,
        agent_id: Optional[str] = None,
        title: Optional[str] = None,
        status: Optional[str] = None,
        current_revision_id: Optional[str] = None,
    ) -> SessionRow:
        session = self.get_session(session_id)
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE contract_sessions
                SET agent_id = ?, title = ?, status = ?, current_revision_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    agent_id if agent_id is not None else session.agent_id,
                    title if title is not None else session.title,
                    status if status is not None else session.status,
                    current_revision_id
                    if current_revision_id is not None
                    else session.current_revision_id,
                    now,
                    session_id,
                ),
            )
            conn.commit()
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete a session and cascaded messages/revisions/exports."""
        self.get_session(session_id)  # raise if missing
        with self._connect() as conn:
            conn.execute("DELETE FROM contract_sessions WHERE id = ?", (session_id,))
            conn.commit()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> MessageRow:
        message_id = _new_id()
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, now),
            )
            conn.execute(
                "UPDATE contract_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
        return MessageRow(message_id, session_id, role, content, now)

    def list_messages(self, session_id: str) -> List[MessageRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            MessageRow(r["id"], r["session_id"], r["role"], r["content"], r["created_at"])
            for r in rows
        ]

    def next_revision_no(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision_no), 0) AS max_no FROM contract_revisions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["max_no"]) + 1

    def add_revision(
        self,
        session_id: str,
        *,
        contract_json: str,
        contract_yaml: str,
        validation_ok: bool,
        validation_errors: Optional[List[str]] = None,
        source_message_id: Optional[str] = None,
        change_summary: Optional[str] = None,
        governance_assessment: Optional[Dict[str, Any]] = None,
    ) -> RevisionRow:
        revision_id = _new_id()
        revision_no = self.next_revision_no(session_id)
        now = _utcnow()
        errors_json = json.dumps(validation_errors or [])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_revisions
                  (id, session_id, revision_no, contract_json, contract_yaml,
                   validation_ok, validation_errors, source_message_id,
                   change_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    session_id,
                    revision_no,
                    contract_json,
                    contract_yaml,
                    1 if validation_ok else 0,
                    errors_json,
                    source_message_id,
                    change_summary,
                    now,
                ),
            )
            if governance_assessment is not None:
                self._insert_assessment_conn(
                    conn,
                    revision_id=revision_id,
                    assessment=governance_assessment,
                    created_at=now,
                )
            conn.execute(
                """
                UPDATE contract_sessions
                SET current_revision_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (revision_id, now, session_id),
            )
            conn.commit()
        return self.get_revision(revision_id)

    def _insert_assessment_conn(
        self,
        conn: sqlite3.Connection,
        *,
        revision_id: str,
        assessment: Dict[str, Any],
        created_at: str,
    ) -> None:
        assessment_id = _new_id()
        conn.execute(
            """
            INSERT INTO revision_governance_assessments
              (id, revision_id, analysis_json, report_json, warnings_json,
               llm_response_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                revision_id,
                json.dumps(assessment.get("analysis")) if assessment.get("analysis") else None,
                json.dumps(assessment.get("report", {})),
                json.dumps(assessment.get("warnings", [])),
                json.dumps(assessment.get("llm_response")) if assessment.get("llm_response") else None,
                created_at,
            ),
        )

    def ensure_governance_snapshot(
        self,
        session_id: str,
        context_snapshot: Dict[str, Any],
    ) -> GovernanceSnapshotRow:
        existing = self.get_governance_snapshot(session_id)
        if existing is not None:
            return existing
        snapshot_id = _new_id()
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO governance_context_snapshots
                  (id, session_id, pack_id, pack_version, context_json, context_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    session_id,
                    context_snapshot.get("pack_id", "roa-dir-v1"),
                    context_snapshot.get("pack_version", "1.0.0"),
                    json.dumps(context_snapshot),
                    context_snapshot.get("context_hash", ""),
                    now,
                ),
            )
            conn.commit()
        return self.get_governance_snapshot(session_id) or GovernanceSnapshotRow(
            id=snapshot_id,
            session_id=session_id,
            pack_id=context_snapshot.get("pack_id", "roa-dir-v1"),
            pack_version=context_snapshot.get("pack_version", "1.0.0"),
            context_json=json.dumps(context_snapshot),
            context_hash=context_snapshot.get("context_hash", ""),
            created_at=now,
        )

    def get_governance_snapshot(self, session_id: str) -> Optional[GovernanceSnapshotRow]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM governance_context_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return GovernanceSnapshotRow(
            id=row["id"],
            session_id=row["session_id"],
            pack_id=row["pack_id"],
            pack_version=row["pack_version"],
            context_json=row["context_json"],
            context_hash=row["context_hash"],
            created_at=row["created_at"],
        )

    def get_governance_assessment(self, revision_id: str) -> Optional[GovernanceAssessmentRow]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM revision_governance_assessments WHERE revision_id = ?",
                (revision_id,),
            ).fetchone()
        if row is None:
            return None
        return GovernanceAssessmentRow(
            id=row["id"],
            revision_id=row["revision_id"],
            analysis_json=row["analysis_json"],
            report_json=row["report_json"],
            warnings_json=row["warnings_json"],
            llm_response_json=row["llm_response_json"],
            created_at=row["created_at"],
        )

    def assessment_warnings(self, assessment: GovernanceAssessmentRow) -> List[str]:
        if not assessment.warnings_json:
            return []
        try:
            parsed = json.loads(assessment.warnings_json)
            return list(parsed) if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return [assessment.warnings_json]

    def get_revision(self, revision_id: str) -> RevisionRow:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contract_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Revision not found: {revision_id}")
        return self._revision_from_row(row)

    def get_current_revision(self, session_id: str) -> Optional[RevisionRow]:
        session = self.get_session(session_id)
        if not session.current_revision_id:
            return None
        return self.get_revision(session.current_revision_id)

    def list_revisions(self, session_id: str) -> List[RevisionRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM contract_revisions
                WHERE session_id = ?
                ORDER BY revision_no ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._revision_from_row(r) for r in rows]

    def add_export(
        self,
        session_id: str,
        revision_id: str,
        emit_mode: str,
        output_paths: List[str],
    ) -> ExportRow:
        export_id = _new_id()
        now = _utcnow()
        paths_json = json.dumps(output_paths)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_exports
                  (id, session_id, revision_id, emit_mode, output_paths, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (export_id, session_id, revision_id, emit_mode, paths_json, now),
            )
            conn.execute(
                "UPDATE contract_sessions SET status = 'exported', updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
        return ExportRow(export_id, session_id, revision_id, emit_mode, paths_json, now)

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> SessionRow:
        return SessionRow(
            id=row["id"],
            agent_id=row["agent_id"],
            title=row["title"],
            preset=row["preset"],
            status=row["status"],
            current_revision_id=row["current_revision_id"],
            llm_provider=row["llm_provider"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> RevisionRow:
        return RevisionRow(
            id=row["id"],
            session_id=row["session_id"],
            revision_no=row["revision_no"],
            contract_json=row["contract_json"],
            contract_yaml=row["contract_yaml"],
            validation_ok=bool(row["validation_ok"]),
            validation_errors=row["validation_errors"],
            source_message_id=row["source_message_id"],
            change_summary=row["change_summary"],
            created_at=row["created_at"],
        )

    def revision_errors(self, revision: RevisionRow) -> List[str]:
        if not revision.validation_errors:
            return []
        try:
            parsed = json.loads(revision.validation_errors)
            return list(parsed) if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return [revision.validation_errors]
