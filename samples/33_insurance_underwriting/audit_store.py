"""
Append-only SQLite audit log for DecisionFlow events (DIR §4.2 telemetry).

Each row: dfid, event, timestamp, step_id, optional state, detail_json.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AuditStore:
    """DFID-tagged decision events and idempotency keys for bind step."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS decision_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dfid TEXT NOT NULL,
                event TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                step_id TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                detail_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_decision_events_dfid ON decision_events(dfid);

            CREATE TABLE IF NOT EXISTS idempotency_keys (
                idempotency_key TEXT PRIMARY KEY,
                dfid TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def record(
        self,
        dfid: str,
        event: str,
        *,
        step_id: str = "",
        state: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        ts = _utc_iso()
        payload = json.dumps(details or {}, sort_keys=True, default=str)
        self._conn.execute(
            """
            INSERT INTO decision_events (dfid, event, timestamp, step_id, state, detail_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (dfid, event, ts, step_id, state, payload),
        )
        self._conn.commit()

    def get_idempotent_result(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT result_json FROM idempotency_keys WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["result_json"])

    def save_idempotent_result(self, key: str, dfid: str, result: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO idempotency_keys (idempotency_key, dfid, result_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, dfid, json.dumps(result, sort_keys=True, default=str), _utc_iso()),
        )
        self._conn.commit()

    def events_for_dfid(self, dfid: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT dfid, event, timestamp, step_id, state, detail_json
            FROM decision_events WHERE dfid = ? ORDER BY id ASC
            """,
            (dfid,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "dfid": r["dfid"],
                    "event": r["event"],
                    "timestamp": r["timestamp"],
                    "step_id": r["step_id"],
                    "state": r["state"],
                    "details": json.loads(r["detail_json"] or "{}"),
                }
            )
        return out

    def all_events_chronological(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT dfid, event, timestamp, step_id, state, detail_json
            FROM decision_events ORDER BY id ASC
            """
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "dfid": r["dfid"],
                    "event": r["event"],
                    "timestamp": r["timestamp"],
                    "step_id": r["step_id"],
                    "state": r["state"],
                    "details": json.loads(r["detail_json"] or "{}"),
                }
            )
        return out
