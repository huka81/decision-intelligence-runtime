"""Tests for Agent Registry handshake and SemVer (DIR §2.3)."""

import tempfile
from pathlib import Path

from dir_core.agent_registry import AgentRegistry, HandshakeResult


def test_handshake_success() -> None:
    """Handshake with compatible version returns ACCEPTED."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        reg = AgentRegistry(path, supported_versions="1.x")
        r = reg.handshake(
            "agent_a",
            {"caps": ["TRADE"]},
            agent_version="1.2",
        )
        assert r.accepted is True
        assert r.session_token is not None
        assert r.reason is None
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_handshake_version_mismatch() -> None:
    """Handshake with incompatible version returns REJECTED."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        reg = AgentRegistry(path, supported_versions="1.x")
        r = reg.handshake(
            "agent_a",
            {"caps": ["TRADE"]},
            agent_version="2.0",
        )
        assert r.accepted is False
        assert r.reason == "VERSION_MISMATCH"
        assert r.session_token is None
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite


def test_get_schema() -> None:
    """get_schema returns schema from contract."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        reg = AgentRegistry(path)
        reg.handshake(
            "agent_a",
            {"schema": {"type": "object"}, "schemas": {"policy": {"x": 1}}},
            agent_version="1.0",
        )
        assert reg.get_schema("agent_a") == {"type": "object"}
        assert reg.get_schema("agent_a", "policy") == {"x": 1}
        assert reg.get_schema("nonexistent") is None
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # Windows: file may be locked by SQLite

