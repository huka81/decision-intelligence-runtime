"""
SQLite audit for Sample 38: decision_flows, market_snapshots, execution_log, decision_events.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AuditStore:
    """DFID-tagged flows, market snapshots (kernel facts), executions, append-only decision events."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS decision_flows (
                dfid TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
                created_at TEXT NOT NULL,
                input_ref TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                dfid TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                market_cpc_to_win REAL NOT NULL,
                captured_at TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (dfid) REFERENCES decision_flows(dfid)
            );
            CREATE INDEX IF NOT EXISTS idx_market_snapshots_dfid ON market_snapshots(dfid);

            CREATE TABLE IF NOT EXISTS execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dfid TEXT NOT NULL,
                cpc_bid_usd REAL NOT NULL,
                executed_at TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (dfid) REFERENCES decision_flows(dfid)
            );
            CREATE INDEX IF NOT EXISTS idx_execution_log_dfid ON execution_log(dfid);

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
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def insert_decision_flow(
        self,
        dfid: str,
        agent_id: str,
        *,
        status: str = "IN_PROGRESS",
        input_ref: str = "",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO decision_flows (dfid, agent_id, status, created_at, input_ref)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dfid, agent_id, status, _utc_iso(), input_ref),
        )
        self._conn.commit()

    def insert_market_snapshot(
        self,
        dfid: str,
        snapshot_id: str,
        market_cpc_to_win: float,
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO market_snapshots (dfid, snapshot_id, market_cpc_to_win, captured_at, detail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                dfid,
                snapshot_id,
                float(market_cpc_to_win),
                _utc_iso(),
                json.dumps(details or {}, sort_keys=True, default=str),
            ),
        )
        self._conn.commit()

    def complete_flow(self, dfid: str, status: str = "COMPLETED") -> None:
        self._conn.execute(
            "UPDATE decision_flows SET status = ? WHERE dfid = ?",
            (status, dfid),
        )
        self._conn.commit()

    def insert_execution(
        self,
        dfid: str,
        cpc_bid_usd: float,
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO execution_log (dfid, cpc_bid_usd, executed_at, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                dfid,
                float(cpc_bid_usd),
                _utc_iso(),
                json.dumps(details or {}, sort_keys=True, default=str),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

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

    def execution_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM execution_log").fetchone()
        return int(row["c"]) if row else 0

    def rolling_cpc_stats(self, window: int) -> Optional[tuple[float, float]]:
        """
        Over the last `window` execution_log rows (by id DESC), join market_snapshots on dfid
        and return (avg_cpc_bid_usd, avg_market_cpc_to_win).

        Both values are meaningful: avg_cpc_bid is actual spend; avg_market_cpc_to_win is the
        authoritative kernel-space fact written at context compile time — proving bids tracked the
        market floor rather than drifting in isolation.

        Returns None if fewer than `window` executions exist.
        """
        if window <= 0:
            return None
        total = self.execution_count()
        if total < window:
            return None
        row = self._conn.execute(
            """
            SELECT AVG(el.cpc_bid_usd) AS avg_bid, AVG(ms.market_cpc_to_win) AS avg_market
            FROM (
              SELECT id, dfid
              FROM execution_log
              ORDER BY id DESC
              LIMIT ?
            ) w
            INNER JOIN execution_log el ON el.id = w.id
            INNER JOIN market_snapshots ms ON ms.dfid = el.dfid
            """,
            (window,),
        ).fetchone()
        if row is None or row["avg_bid"] is None or row["avg_market"] is None:
            return None
        return float(row["avg_bid"]), float(row["avg_market"])

    def list_executions_chronological(self) -> List[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT el.id, el.dfid, el.cpc_bid_usd, el.executed_at, el.detail_json,
                   df.agent_id, df.status AS flow_status, df.input_ref,
                   ms.market_cpc_to_win, ms.snapshot_id
            FROM execution_log el
            INNER JOIN decision_flows df ON df.dfid = el.dfid
            INNER JOIN market_snapshots ms ON ms.dfid = el.dfid
            ORDER BY el.id ASC
            """
        ).fetchall()
        out: List[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "dfid": r["dfid"],
                    "cpc_bid_usd": r["cpc_bid_usd"],
                    "executed_at": r["executed_at"],
                    "details": json.loads(r["detail_json"] or "{}"),
                    "agent_id": r["agent_id"],
                    "flow_status": r["flow_status"],
                    "input_ref": r["input_ref"],
                    "market_cpc_to_win": r["market_cpc_to_win"],
                    "snapshot_id": r["snapshot_id"],
                }
            )
        return out

    def list_monitor_events(self) -> List[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT dfid, event, timestamp, state, detail_json
            FROM decision_events
            WHERE event LIKE 'MONITOR_%' OR event = 'AGENT_SUSPENDED'
            ORDER BY id ASC
            """
        ).fetchall()
        return [
            {
                "dfid": r["dfid"],
                "event": r["event"],
                "timestamp": r["timestamp"],
                "state": r["state"],
                "details": json.loads(r["detail_json"] or "{}"),
            }
            for r in rows
        ]
