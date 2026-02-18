"""
ExecutionEngine - Simulates Payment Gateway API call.

DIR §7: Only validated intents trigger side effects. This engine simulates
the external Payment Gateway. No actual network calls.
"""

import logging

try:
    from .schemas import DecisionAtom
except ImportError:
    from schemas import DecisionAtom

logger = logging.getLogger(__name__)


def execute(atom: DecisionAtom, tx_id: str) -> None:
    """
    Simulate Payment Gateway execution.

    Only called when JIT validation passed and action is ALLOW.
    Logs the "API call" for demonstration.
    """
    logger.info(
        f"[DFID={atom.dfid}] PaymentGateway: ALLOW tx_id={tx_id} "
        f"user={atom.user_id} amount={atom.amount} reason={atom.reason_code}"
    )
