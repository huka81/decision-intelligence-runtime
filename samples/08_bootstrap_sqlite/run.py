#!/usr/bin/env python3
"""
08_bootstrap_sqlite - Ensure DB and tables exist before use.
Run from repo root: python samples/08_bootstrap_sqlite/run.py
Requires PYTHONPATH including workspace src/ (see .vscode/settings.json).
"""
import sqlite3
from pathlib import Path

from dir.bootstrap_sqlite import ensure_db


def create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS decision_flows (dfid TEXT PRIMARY KEY, status TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sample_events (id INTEGER PRIMARY KEY, dfid TEXT, event_type TEXT)"
    )


def main() -> None:
    data_dir = Path(__file__).resolve().parent / "data"
    db_path = data_dir / "sample.db"
    path = ensure_db(db_path, create_tables=create_tables)
    print(f"[SUMMARY] DB ready: {path}")


if __name__ == "__main__":
    main()
