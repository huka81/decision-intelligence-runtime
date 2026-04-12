"""
Idempotency Guard (DIR §7) - ensures operations are executed exactly once.

Key is formed from:
- DFID (decision flow ID)
- Step ID (unique within flow)
- Canonical parameters (sorted JSON)

Backend can be in-memory (testing) or persistent (production). The built-in
backends are :class:`MemoryBackend` and :class:`SQLiteBackend`; custom backends
must satisfy the :class:`IdempotencyBackend` protocol.
"""

import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional, Protocol

from .storage.memory import MemoryIdempotencyStorage
from .storage.sqlite import SqliteIdempotencyStorage

logger = logging.getLogger(__name__)


def idempotency_key(dfid: str, step_id: str, params: Dict[str, Any]) -> str:
    """Compute deterministic key: SHA256(dfid|step_id|canonical_params)."""
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{dfid}:{step_id}:{canonical}"
    return hashlib.sha256(raw.encode()).hexdigest()


class IdempotencyBackend(Protocol):
    """Protocol satisfied by all idempotency storage backends."""

    def get(self, key: str) -> Optional[Dict[str, Any]]: ...
    def set(self, key: str, result: Dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

#: In-memory backend — alias for :class:`~dir_core.storage.MemoryIdempotencyStorage`.
MemoryBackend = MemoryIdempotencyStorage

#: SQLite-backed persistent backend — alias for
#: :class:`~dir_core.storage.SqliteIdempotencyStorage`.
SQLiteBackend = SqliteIdempotencyStorage


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class IdempotencyGuard:
    """Guard that checks cache before execution and records result after.

    Args:
        backend: Any object satisfying :class:`IdempotencyBackend`
            (e.g. ``MemoryBackend()``, ``SQLiteBackend("cache.db")``,
            or a custom implementation).
    """

    def __init__(self, backend: IdempotencyBackend):
        self.backend = backend

    def run(self, dfid: str, step_id: str, params: Dict[str, Any], func: Callable[..., Any]) -> Any:
        """Run func(params) with idempotency protection."""
        key = idempotency_key(dfid, step_id, params)

        cached = self.backend.get(key)
        if cached is not None:
            logger.info(f"[Idempotency] HIT key={key[:8]}...")
            return cached

        logger.info(f"[Idempotency] MISS key={key[:8]}... Executing.")
        result = func(**params)

        self.backend.set(key, result)
        return result
