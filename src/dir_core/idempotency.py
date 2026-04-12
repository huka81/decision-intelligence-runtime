"""
Idempotency Guard (DIR §7) - ensures operations are executed exactly once.

Key is formed from:
- DFID (decision flow ID)
- Step ID (unique within flow)
- Canonical parameters (sorted JSON)

Backend can be in-memory (testing) or SQLite (production/persistence).
"""

import hashlib
import json
import sqlite3
import logging
from typing import Any, Callable, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


def idempotency_key(dfid: str, step_id: str, params: Dict[str, Any]) -> str:
    """Compute deterministic key: SHA256(dfid|step_id|canonical_params)."""
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{dfid}:{step_id}:{canonical}"
    return hashlib.sha256(raw.encode()).hexdigest()


class IdempotencyBackend(Protocol):
    def get(self, key: str) -> Optional[Dict[str, Any]]: ...
    def set(self, key: str, result: Dict[str, Any]) -> None: ...


class MemoryBackend:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(key)

    def set(self, key: str, result: Dict[str, Any]) -> None:
        self._cache[key] = result


class SQLiteBackend:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_cache (
                    key TEXT PRIMARY KEY,
                    result JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT result FROM idempotency_cache WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

    def set(self, key: str, result: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO idempotency_cache (key, result) VALUES (?, ?)",
                (key, json.dumps(result))
            )
            conn.commit()


class IdempotencyGuard:
    """Guard that checks cache before execution and records result after."""

    def __init__(self, backend: IdempotencyBackend):
        self.backend = backend

    def run(self, dfid: str, step_id: str, params: Dict[str, Any], func: Callable[..., Any]) -> Any:
        """Run func(params) with idempotency protection."""
        key = idempotency_key(dfid, step_id, params)
        
        # 1. Check cache
        cached = self.backend.get(key)
        if cached is not None:
            logger.info(f"[Idempotency] HIT key={key[:8]}...")
            return cached

        # 2. Execute
        logger.info(f"[Idempotency] MISS key={key[:8]}... Executing.")
        result = func(**params)

        # 3. Store result
        self.backend.set(key, result)
        return result
