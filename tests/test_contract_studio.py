"""Tests for Contract Studio web app and persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from tools.contract.db.store import ContractStudioStore
from tools.contract.llm_interview import (
    empty_draft_contract,
    mock_contract_llm_strategy,
    process_chat_turn,
)
from samples.shared.llm.clients import MockLLMClient


@pytest.fixture
def studio_db(tmp_path: Path) -> ContractStudioStore:
    return ContractStudioStore(tmp_path / "test_studio.db")


def test_store_session_and_revision(studio_db: ContractStudioStore) -> None:
    session = studio_db.create_session(title="Test", preset="trading")
    studio_db.add_message(session.id, "user", "hello")
    draft = empty_draft_contract("trading")
    from tools.contract.governance.context import build_governance_context

    snapshot = build_governance_context(preset="trading", role="EXECUTOR")
    studio_db.ensure_governance_snapshot(session.id, snapshot)
    rev = studio_db.add_revision(
        session.id,
        contract_json=json.dumps(draft),
        contract_yaml="# draft",
        validation_ok=False,
        validation_errors=["missing limits"],
        governance_assessment={
            "analysis": {"goal": {"objective": "test"}},
            "report": {"blocking_ok": False},
            "warnings": ["GOAL_NO_SOURCE: test warning"],
        },
    )
    studio_db.update_session(session.id, current_revision_id=rev.id)
    loaded = studio_db.get_current_revision(session.id)
    assert loaded is not None
    assert loaded.revision_no == 1
    assert studio_db.list_messages(session.id)
    assessment = studio_db.get_governance_assessment(rev.id)
    assert assessment is not None
    assert studio_db.get_governance_snapshot(session.id) is not None


def test_process_chat_turn_mock() -> None:
    llm = MockLLMClient(strategy=mock_contract_llm_strategy)
    current = empty_draft_contract("trading")
    turn = process_chat_turn(
        llm,
        current_contract=current,
        chat_history=[],
        user_message="I need a crypto trading agent",
        preset="trading",
    )
    assert "contract" in turn.assistant_reply.lower() or "trading" in turn.assistant_reply.lower()
    assert turn.merged_contract["subject"]["agent_id"] == "trading_bot_01"
    assert turn.merged_contract["metadata"]["owner"] == "jane.doe@example.com"
    assert turn.merged_contract["authority"]["limits"]["max_order_size_usd"] == {
        "value": 50000.0,
        "unit": "USD",
    }
    assert "api_version: roa.dir/v1" in turn.contract_yaml
    assert turn.validation_ok is True
    assert not turn.blocking_errors
    assert turn.governance_analysis is not None
    assert turn.change_summary


@pytest.fixture
def studio_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.setenv("CONTRACT_STUDIO_DB", str(tmp_path / "api_test.db"))

    from tools.contract.web.app import create_app

    return TestClient(create_app())


def test_api_create_chat_export(studio_client) -> None:
    res = studio_client.post("/api/sessions", json={"title": "API test", "preset": "trading"})
    assert res.status_code == 200
    session_id = res.json()["session"]["id"]
    assert res.json().get("governance_context_hash")

    chat = studio_client.post(
        f"/api/sessions/{session_id}/chat",
        json={"message": "Build a crypto trading agent with limits"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["validation_ok"] is True
    assert "trading_bot_01" in body["contract_yaml"]
    assert body.get("governance_analysis") is not None

    validate = studio_client.post(
        f"/api/sessions/{session_id}/validate",
        json={"yaml": body["contract_yaml"]},
    )
    assert validate.status_code == 200
    vbody = validate.json()
    assert vbody["integrity_ok"] is True
    assert vbody["checks"]["yaml_parse"]["ok"] is True
    assert vbody["checks"]["schema"]["ok"] is True
    assert vbody["checks"]["bootstrap"]["ok"] is True
    assert vbody["sha256"]

    export = studio_client.post(
        f"/api/sessions/{session_id}/export",
        json={"emit": "registry"},
    )
    assert export.status_code == 200
    paths = export.json()["paths"]
    assert any(p.endswith(".yaml") for p in paths)
    assert Path(paths[0]).is_file()

    revisions = studio_client.get(f"/api/sessions/{session_id}/revisions")
    assert revisions.status_code == 200
    assert len(revisions.json()["revisions"]) >= 2


def test_api_manual_yaml_edit_saves_new_revision(studio_client) -> None:
    res = studio_client.post("/api/sessions", json={"title": "Manual", "preset": "trading"})
    session_id = res.json()["session"]["id"]
    chat = studio_client.post(
        f"/api/sessions/{session_id}/chat",
        json={"message": "Build a crypto trading agent with limits"},
    )
    original_yaml = chat.json()["contract_yaml"]
    revisions_before = len(
        studio_client.get(f"/api/sessions/{session_id}/revisions").json()["revisions"]
    )

    edited = original_yaml.replace("value: 50000.0", "value: 12345.0")
    assert edited != original_yaml

    saved = studio_client.put(
        f"/api/sessions/{session_id}/contract",
        json={"yaml": edited},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["saved"] is True
    assert body["validation_ok"] is True
    assert "value: 12345.0" in body["contract_yaml"]

    reloaded = studio_client.get(f"/api/sessions/{session_id}").json()
    assert "value: 12345.0" in reloaded["contract_yaml"]
    assert reloaded["session"]["status"] == "ready"
    revisions_after = studio_client.get(
        f"/api/sessions/{session_id}/revisions"
    ).json()["revisions"]
    assert len(revisions_after) == revisions_before + 1
    assert revisions_after[-1]["change_summary"] == "Manual YAML edit"


def test_api_manual_yaml_edit_rejects_broken_yaml(studio_client) -> None:
    res = studio_client.post("/api/sessions", json={"title": "Broken", "preset": "trading"})
    session_id = res.json()["session"]["id"]
    chat = studio_client.post(
        f"/api/sessions/{session_id}/chat",
        json={"message": "Build a crypto trading agent with limits"},
    )
    good_yaml = chat.json()["contract_yaml"]

    broken = studio_client.put(
        f"/api/sessions/{session_id}/contract",
        json={"yaml": "authority: [not: valid: {{{"},
    )
    assert broken.status_code == 200
    assert broken.json()["saved"] is False
    assert broken.json()["validation_errors"]

    empty = studio_client.put(
        f"/api/sessions/{session_id}/contract",
        json={"yaml": "   "},
    )
    assert empty.status_code == 400

    # Rejected edits leave the stored revision untouched.
    assert studio_client.get(f"/api/sessions/{session_id}").json()["contract_yaml"] == good_yaml


def test_api_manual_yaml_edit_reports_bootstrap_failure(studio_client) -> None:
    res = studio_client.post("/api/sessions", json={"title": "NoLimits", "preset": "trading"})
    session_id = res.json()["session"]["id"]

    without_limits = """
api_version: roa.dir/v1
kind: ResponsibilityContract
metadata:
  contract_id: trading_bot_01
  version: 1.0.0
  owner: owner@example.com
subject:
  agent_id: trading_bot_01
  role: EXECUTOR
mission:
  statement: Trade within mandate.
authority:
  allowed_policy_types: [BUY, SELL]
  limits: {}
"""
    saved = studio_client.put(
        f"/api/sessions/{session_id}/contract",
        json={"yaml": without_limits},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["saved"] is True
    assert body["validation_ok"] is False
    assert body["validation_errors"]
    assert body["status"] == "drafting"

    export = studio_client.post(
        f"/api/sessions/{session_id}/export", json={"emit": "registry"}
    )
    assert export.status_code == 400


def test_index_serves_versioned_assets(studio_client) -> None:
    res = studio_client.get("/")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    assert "__ASSET_VERSION__" not in res.text
    assert 'id="yamlEditor"' in res.text
    assert "/static/app.js?v=" in res.text
    assert "/static/styles.css?v=" in res.text


def test_verify_contract_yaml_rejects_garbage() -> None:
    from tools.contract.integrity import verify_contract_yaml

    result = verify_contract_yaml("not: [valid: yaml: {{{")
    assert result["integrity_ok"] is False
    assert result["checks"]["yaml_parse"]["ok"] is False


def test_rename_and_delete_session(studio_client) -> None:
    a = studio_client.post("/api/sessions", json={"title": "Alpha", "preset": "generic"})
    b = studio_client.post("/api/sessions", json={"title": "Beta", "preset": "trading"})
    assert a.status_code == 200 and b.status_code == 200
    id_a = a.json()["session"]["id"]
    id_b = b.json()["session"]["id"]

    renamed = studio_client.patch(f"/api/sessions/{id_a}", json={"title": "Alpha Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["session"]["title"] == "Alpha Renamed"

    deleted = studio_client.delete(f"/api/sessions/{id_b}")
    assert deleted.status_code == 200
    listed = studio_client.get("/api/sessions").json()["sessions"]
    ids = {s["id"] for s in listed}
    assert id_a in ids
    assert id_b not in ids
    assert any(s["title"] == "Alpha Renamed" for s in listed)


def test_normalize_nested_irreversible_limits_alias() -> None:
    from tools.contract.integrity import verify_contract_yaml
    from tools.contract.schema import normalize_contract_dict

    raw = {
        "agent_id": "retention_executor_agent",
        "version": "1.0.0",
        "owner": "ja@outlook.com",
        "role": "EXECUTOR",
        "mission": "Retention actions with discounts.",
        "authority": {
            "authorized_instruments": ["RETENTION_DISCOUNT"],
            "allowed_policy_types": ["ACTION", "HOLD"],
            "irreversible_limits": {"max_discount_percentage": 15.0},
        },
        "responsibility": {
            "explainability": "required",
            "evidence_level": "medium",
            "escalation": "mandatory",
            "escalate_on_uncertainty": 0.7,
        },
    }
    normalized = normalize_contract_dict(raw)
    assert normalized["authority"]["limits"]["max_discount_pct"] == {
        "value": 15.0,
        "unit": "percent",
    }
    assert normalized["authority"]["resource_scope"]["instruments"] == [
        "RETENTION_DISCOUNT"
    ]
    assert normalized["responsibility"]["escalation"] == {
        "mode": "mandatory",
        "confidence_below": 0.7,
    }

    yaml_text = """
agent_id: retention_executor_agent
version: 1.0.0
owner: ja@outlook.com
role: EXECUTOR
mission: Retention actions with discounts.
authority:
  allowed_policy_types: [ACTION, HOLD]
  irreversible_limits:
    max_discount_percentage: 15.0
responsibility:
  explainability: required
  evidence_level: medium
  escalation: mandatory
  escalate_on_uncertainty: 0.7
"""
    result = verify_contract_yaml(yaml_text, preset="generic")
    assert result["integrity_ok"] is True
    assert result["checks"]["bootstrap"]["ok"] is True
