"""
In-memory Redis mock for user risk scores.

Simulates a global risk service (e.g., Redis-backed) that external systems
update when accounts are flagged (e.g., "Compromised"). Enables the drift-attack
scenario: snapshot at T=0 shows "clean", but at T+50ms the account is flagged.
"""

import time
from typing import Literal, Optional

Status = Literal["clean", "compromised"]


class RiskCache:
    """In-memory mock of Redis-like risk state store."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, user_id: str) -> Optional[dict]:
        """Get current risk state for user."""
        return self._data.get(user_id)

    def set(self, user_id: str, status: Status, risk_score: float) -> None:
        """Set risk state (creates or overwrites)."""
        self._data[user_id] = {
            "risk_score": risk_score,
            "status": status,
            "updated_at": time.monotonic(),
        }

    def get_snapshot(self, user_id: str) -> Optional[dict]:
        """Get current state as would be captured in a snapshot."""
        return self.get(user_id)

    def flag_compromised(self, user_id: str, risk_score: float = 1.0) -> None:
        """Simulate external system flagging account as compromised."""
        self.set(user_id, "compromised", risk_score)
