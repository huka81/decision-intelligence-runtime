"""
Idempotency key and cache: SHA256(DFID + step_id + canonical_params).

DIR §7. Stub for MVP; implement when building sample 3.
"""

import hashlib
import json
from typing import Any, Dict, Optional

def idempotency_key(dfid: str, step_id: str, params: Dict[str, Any]) -> str:
    """Compute deterministic key. Canonical params = sorted JSON."""
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{dfid}|{step_id}|{canonical}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached_result(key: str) -> Optional[Dict[str, Any]]:
    """Return cached result for key if present. Stub: returns None."""
    return None


def set_cached_result(key: str, result: Dict[str, Any]) -> None:
    """Store result for key. Stub: no-op."""
    pass
