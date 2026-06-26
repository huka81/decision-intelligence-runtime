"""
Decision Ledger (Topology C §5.4) — append-only, verified decisions only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import ProofCarryingIntent
from .storage.base import DecisionLedgerStorage

logger = logging.getLogger(__name__)


def _entry_from_pci(pci: ProofCarryingIntent) -> Dict[str, Any]:
    return {
        "dfid": pci.dfid,
        "intent_payload": pci.intent_payload,
        "context_ref": pci.context_ref,
        "evidence_hash": pci.evidence_hash,
        "signature": pci.signature or "",
    }


class DecisionLedger:
    """
    Append-only store for verified PCIs only.

    Unverified decisions must never become binding. The Ledger is the source
    of truth; only DIM-approved entries are appended. This prevents "Day Two"
    failures where hallucinated or forged agent outputs become operational.

    When *storage* is provided, entries are persisted via
    :class:`~dir_core.storage.base.DecisionLedgerStorage` (e.g.
    ``decision_ledger_entries`` in SQLite). Otherwise entries live in process
    memory only.
    """

    def __init__(self, storage: Optional[DecisionLedgerStorage] = None) -> None:
        self._storage = storage
        self._memory: List[Dict[str, Any]] = []

    def append(
        self, pci: ProofCarryingIntent, *, agent_id: str
    ) -> None:
        """Append a verified PCI. Called only by DIM after successful verification."""
        if self._storage is not None:
            self._storage.append(pci, agent_id=agent_id)
            count = len(self._storage.all_entries_chronological())
        else:
            entry = _entry_from_pci(pci)
            self._memory.append(entry)
            count = len(self._memory)
        logger.info(
            "[DFID=%s] Ledger appended entry #%d. Policy Bound.",
            pci.dfid[:8],
            count,
        )

    def entries(self) -> List[Dict[str, Any]]:
        """Return all ledger entries (read-only copy)."""
        if self._storage is not None:
            return self._storage.all_entries_chronological()
        return list(self._memory)

    def __len__(self) -> int:
        if self._storage is not None:
            return len(self._storage.all_entries_chronological())
        return len(self._memory)
