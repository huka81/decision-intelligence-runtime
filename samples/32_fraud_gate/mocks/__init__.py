"""
``32_fraud_gate`` test doubles — anything that replaces a real external dependency.

* ``external_risk_store`` — fake Redis / risk API rows (drift demo).
* ``llm_mock_strategy`` — deterministic ``MockLLMClient`` responses.
* ``live_risk_projection`` — DIM-facing projection from the risk fake.
* ``settlement_mock`` — fake PSP / idempotent settlement log.

Kernel code lives under ``src/dir_core``; business rules in the sample root
(``agent``, ``dim``, ``schemas``); canonical persistence via ``telemetry`` +
``StorageBundle`` from ``shared.bootstrap``.
"""

from .external_risk_store import InMemoryRiskStore
from .live_risk_projection import live_risk_rows_from_store
from .llm_mock_strategy import make_mock_strategy
from .settlement_mock import (
    execute_mock_allow_settlement,
    log_mock_gateway_non_allow,
    payment_idempotency_key,
)

__all__ = [
    "InMemoryRiskStore",
    "execute_mock_allow_settlement",
    "live_risk_rows_from_store",
    "log_mock_gateway_non_allow",
    "make_mock_strategy",
    "payment_idempotency_key",
]
