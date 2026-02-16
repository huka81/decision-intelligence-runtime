"""
Bootstrap SQLite: ensure DB file and required tables exist before running a sample.

Used by any sample that needs SQLite (context store, ledger, idempotency cache, registry).
"""

import sqlite3
from pathlib import Path
from typing import Callable, Optional


def ensure_db(path: Path, create_tables: Optional[Callable[[sqlite3.Connection], None]] = None) -> Path:
    """
    If path does not exist, create parent dir and empty DB; then run create_tables(conn).
    Returns path. create_tables can create schema (e.g. decision_flows, idempotency_cache).
    """
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        if create_tables:
            create_tables(conn)
        conn.commit()
    finally:
        conn.close()
    return path
