"""
Canonical JSON encoding for storage rows (audit details, idempotency payloads).

Keeps SQLite and external PostgreSQL repositories aligned on serialization so
callers can mix backends without divergent handling of datetimes, UUIDs, etc.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def dumps_json_dict(data: Dict[str, Any], *, sort_keys: bool = True) -> str:
    """Serialize a dict for TEXT / JSONB columns.

    Uses stable key order and ``default=str`` so values that are not native
    JSON types (e.g. ``datetime``, UUID) encode consistently in
    :class:`~dir_core.storage.sqlite.SqliteDecisionAuditStorage` and in the
    sample PostgreSQL repository (``samples/shared/storage/pg_repo.py``).
    """
    return json.dumps(data, sort_keys=sort_keys, default=str)
