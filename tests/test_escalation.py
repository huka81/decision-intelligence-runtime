"""Tests for Escalation Manager (DIR §9)."""

import tempfile
from pathlib import Path

from dir_core.escalation import (
    EscalationManager,
    EscalationOutcome,
    ImpactCategory,
)
from dir_core.models import EscalationRequest, Policy, PolicyProposal


def test_request_escalation_granted() -> None:
    """First escalation in window is GRANTED."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        em = EscalationManager(path, max_escalations_per_hour=3)
        proposal = PolicyProposal(
            dfid="d1", agent_id="a1", policy_kind="TRADE"
        )
        outcome = em.request_escalation(
            "d1", "a1", "RISK_LIMIT", {"x": 1}, proposal, ImpactCategory.HIGH_IMPACT
        )
        assert outcome == EscalationOutcome.GRANTED
        pending = em.get_pending()
        assert len(pending) == 1
        assert pending[0]["dfid"] == "d1"
        assert pending[0]["reason"] == "RISK_LIMIT"
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_budget_exhausted() -> None:
    """After max_escalations_per_hour, BUDGET_EXHAUSTED."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        em = EscalationManager(path, max_escalations_per_hour=2)
        proposal = PolicyProposal(
            dfid="d1", agent_id="a1", policy_kind="TRADE"
        )
        assert em.request_escalation(
            "d1", "a1", "r1", {}, proposal, ImpactCategory.LOW_IMPACT
        ) == EscalationOutcome.GRANTED
        assert em.request_escalation(
            "d2", "a1", "r2", {}, proposal, ImpactCategory.LOW_IMPACT
        ) == EscalationOutcome.GRANTED
        assert em.request_escalation(
            "d3", "a1", "r3", {}, proposal, ImpactCategory.LOW_IMPACT
        ) == EscalationOutcome.BUDGET_EXHAUSTED
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_resolve_escalation() -> None:
    """resolve_escalation records decision."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        em = EscalationManager(path)
        proposal = PolicyProposal(
            dfid="d1", agent_id="a1", policy_kind="TRADE"
        )
        em.request_escalation(
            "d1", "a1", "r1", {}, proposal, ImpactCategory.HIGH_IMPACT
        )
        em.resolve_escalation("d1", "OVERRIDE")
        pending = em.get_pending()
        assert len(pending) == 0
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_request_from_model() -> None:
    """request_from_model maps EscalationRequest to request_escalation API."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        em = EscalationManager(path, max_escalations_per_hour=3)
        policy = Policy(
            dfid="e1",
            agent_id="a1",
            proposed_action="BUY",
            justification="test",
            confidence=0.8,
        )
        req = EscalationRequest(
            dfid="e1",
            from_agent_id="a1",
            trigger="UNCERTAINTY",
            context={"risk": 0.9},
            original_policy=policy,
            severity="HIGH",
        )
        outcome = em.request_from_model(req)
        assert outcome == EscalationOutcome.GRANTED
        pending = em.get_pending()
        assert len(pending) == 1
        assert pending[0]["dfid"] == "e1"
        assert pending[0]["reason"] == "UNCERTAINTY"
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass

