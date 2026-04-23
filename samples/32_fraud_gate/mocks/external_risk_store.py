"""
In-memory stand-in for an external risk / account-status service (e.g. Redis).

Production would query a real API; this sample keeps mutable user state in RAM
so the drift scenario can flip ``clean`` -> ``compromised`` after the agent proposes.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

Status = Literal["clean", "compromised"]


class InMemoryRiskStore:
    """Process-local fake of a global risk row store."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, user_id: str) -> Optional[dict]:
        return self._data.get(user_id)

    def set(self, user_id: str, status: Status, risk_score: float) -> None:
        self._data[user_id] = {
            "risk_score": risk_score,
            "status": status,
            "updated_at": time.monotonic(),
        }

    def get_snapshot(self, user_id: str) -> Optional[dict]:
        return self.get(user_id)

    def flag_compromised(self, user_id: str, risk_score: float = 1.0) -> None:
        """Simulate another system flagging the account after the agent decided."""
        self.set(user_id, "compromised", risk_score)
