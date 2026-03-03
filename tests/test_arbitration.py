"""Tests for dir.arbitration module."""

from dir.arbitration import DEFAULT_PRIORITY_MATRIX, select_winner
from dir.models import PolicyProposal


def _proposal(agent_id: str, policy_kind: str) -> PolicyProposal:
    return PolicyProposal(
        dfid="test-dfid",
        agent_id=agent_id,
        policy_kind=policy_kind,
        params={},
    )


def test_select_winner_empty() -> None:
    assert select_winner([]) is None


def test_select_winner_single() -> None:
    p = _proposal("a1", "HOLD")
    assert select_winner([p]) is p


def test_select_winner_priority() -> None:
    hold = _proposal("a1", "HOLD")
    risk = _proposal("a2", "RISK_ALERT")
    assert select_winner([hold, risk]) is risk
    assert select_winner([risk, hold]) is risk


def test_select_winner_custom_matrix() -> None:
    a = _proposal("a1", "CUSTOM_HIGH")
    b = _proposal("a2", "CUSTOM_LOW")
    matrix = {"CUSTOM_HIGH": 1, "CUSTOM_LOW": 5}
    assert select_winner([a, b], matrix) is a


def test_default_priority_matrix() -> None:
    assert DEFAULT_PRIORITY_MATRIX["RISK_ALERT"] == 1
    assert DEFAULT_PRIORITY_MATRIX["HOLD"] == 10
