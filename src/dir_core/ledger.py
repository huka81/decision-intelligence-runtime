"""
Decision Ledger (Topology C §4.2) — append-only, verified decisions only.
"""

import logging
from typing import Any, Dict, List

from .models import ProofCarryingIntent

logger = logging.getLogger(__name__)


class DecisionLedger:
    """
    Append-only list storing only verified decisions.

    Unverified decisions must never become binding. The Ledger is the source
    of truth; only DIM-approved entries are appended. This prevents "Day Two"
    failures where hallucinated or forged agent outputs become operational.
    """

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []

    def append(self, pci: ProofCarryingIntent) -> None:
        """Append a verified PCI. Called only by DIM after successful verification."""
        entry = {
            "dfid": pci.dfid,
            "intent_payload": pci.intent_payload,
            "evidence_hash": pci.evidence_hash,
        }
        self._entries.append(entry)
        logger.info(
            "[DFID=%s] Ledger appended entry #%d. Policy Bound.",
            pci.dfid[:8],
            len(self._entries),
        )

    def entries(self) -> List[Dict[str, Any]]:
        """Return all ledger entries (read-only copy)."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
