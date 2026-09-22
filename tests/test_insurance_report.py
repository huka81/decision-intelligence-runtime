"""Audit-only HTML reconstruction for sample 33."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_DIR = _REPO_ROOT / "samples" / "33_insurance_underwriting"
for _path in (
    _REPO_ROOT,
    _REPO_ROOT / "src",
    _REPO_ROOT / "samples",
    _SAMPLE_DIR,
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from dir_core.storage import AuditStore, memory_storage
from shared.config import load_yaml_config

from report_generator import group_events_by_dfid, terminal_outcome, write_underwriting_html_report
from telemetry import record_underwriting_step, record_simulation_start, record_simulation_end


def test_terminal_outcome_from_audit_events() -> None:
    bundle = memory_storage()
    audit = AuditStore(bundle.decision_audit, bundle.idempotency)
    dfid = "dfid-report-test"
    simulation_id = "uw_report_test"

    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "MAIL_INGESTED",
        state="CREATED",
        details={"file": "fixture.md", "subject": "Test", "mail_body_sha256": "abc"},
        agent_id="underwriter_agent",
    )
    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "FLOW_TERMINAL",
        state="ABORTED",
        details={
            "outcome": "REJECTED",
            "reason_code": "PROHIBITED_TERRITORY",
            "lifecycle_state": "ABORTED",
        },
        agent_id="underwriter_agent",
    )

    events = audit.all_events_chronological()
    grouped = group_events_by_dfid(events)
    assert dfid in grouped
    terminal = terminal_outcome(grouped[dfid])
    assert terminal["outcome"] == "REJECTED"
    assert terminal["reason_code"] == "PROHIBITED_TERRITORY"


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("markdown") is None,
    reason="markdown package required for HTML report rendering",
)
def test_write_underwriting_html_report_readable_layout(tmp_path: Path) -> None:
    bundle = memory_storage()
    audit = AuditStore(bundle.decision_audit, bundle.idempotency)
    simulation_id = "uw_report_layout_test"
    dfid = "dfid-report-layout"
    config = load_yaml_config(_SAMPLE_DIR / "config.yaml")

    record_simulation_start(audit, simulation_id, config=config)
    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "MAIL_INGESTED",
        state="CREATED",
        details={
            "file": "fixture.md",
            "subject": "Readable Report Test",
            "mail_body_sha256": "abc123",
        },
        agent_id="underwriter_agent",
    )
    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "POLICY_PROPOSED",
        state="ACTIVE",
        details={
            "total_insured_value": 1_850_000,
            "territory": "United Kingdom",
            "justification": "Within delegated authority.",
        },
        agent_id="underwriter_agent",
    )
    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "PCI_EMITTED",
        state="VALIDATING",
        details={
            "total_insured_value": 1_850_000,
            "territory": "United Kingdom",
            "justification": "Within delegated authority.",
            "evidence_hash": "deadbeef" * 8,
        },
        agent_id="underwriter_agent",
    )
    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "DIM_RESULT",
        state="VALIDATING",
        details={"result": "Policy Bound", "reason_codes": []},
        agent_id="underwriter_agent",
    )
    record_underwriting_step(
        audit,
        dfid,
        simulation_id,
        "FLOW_TERMINAL",
        state="CLOSED",
        details={
            "outcome": "BOUND",
            "reason_code": "POLICY_BOUND",
            "lifecycle_state": "CLOSED",
            "policy_ref": "POL-TEST123",
        },
        agent_id="underwriter_agent",
    )
    record_simulation_end(audit, simulation_id, status="ok", agent_id="underwriter_agent")

    out = tmp_path / "report.html"
    write_underwriting_html_report(
        bundle,
        simulation_id=simulation_id,
        sample_dir=_SAMPLE_DIR,
        config=config,
        output_path=out,
    )
    html = out.read_text(encoding="utf-8")

    assert "Decision rationale" in html
    assert "$1,850,000" in html
    assert "Processing timeline" in html
    assert "Policy + PCI" in html
    assert '"simulation_id"' not in html
    assert "TiV $1,850,000" in html
