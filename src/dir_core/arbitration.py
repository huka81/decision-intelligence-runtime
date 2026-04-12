"""
Priority-Based Arbitration (DIR Topologies §2.4).

Selects the winning proposal from parallel agents using a priority matrix.
Lower priority number = higher precedence (e.g. Risk > Strategy).
"""

from typing import Dict, List, Optional

from .models import PolicyProposal

DEFAULT_PRIORITY_MATRIX: Dict[str, int] = {
    "RISK_ALERT": 1,
    "CLOSE_LONG": 2,
    "CLOSE": 2,
    "OPEN_LONG": 3,
    "TAKE_PROFIT": 3,
    "ADJUST_STOP": 4,
    "SENTIMENT_BULLISH": 4,
    "SENTIMENT_BEARISH": 4,
    "RISK_OK": 5,
    "OPEN_POSITION": 5,
    "NEWS_QUALIFIED": 6,
    "SENTIMENT_NEUTRAL": 7,
    "HOLD": 10,
}


def select_winner(
    proposals: List[PolicyProposal],
    priority_matrix: Optional[Dict[str, int]] = None,
) -> Optional[PolicyProposal]:
    """Select winning proposal using Priority Matrix (Topologies §2.4).

    Lower priority number = higher precedence. If no matrix provided,
    uses DEFAULT_PRIORITY_MATRIX. Unknown policy_kind gets priority 10.

    Args:
        proposals: List of policy proposals from parallel agents.
        priority_matrix: Optional mapping policy_kind -> priority (lower = higher).

    Returns:
        The winning proposal, or None if proposals list is empty.
    """
    if not proposals:
        return None

    matrix = priority_matrix or DEFAULT_PRIORITY_MATRIX

    def get_priority(p: PolicyProposal) -> int:
        return matrix.get(p.policy_kind, 10)

    return min(proposals, key=get_priority)
