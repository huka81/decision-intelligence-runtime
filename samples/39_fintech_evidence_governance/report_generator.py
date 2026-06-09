"""HTML audit report — scenario-grouped, pipeline-stage verdicts."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dir_core.storage import StorageBundle

from approval_monitor import is_drift_batch_execution
from schemas import ScenarioConfig, load_scenarios
from shared.config import load_yaml_config

# Pipeline stages shown left-to-right in each scenario card
PIPELINE_STAGES: List[Tuple[str, str]] = [
    ("evidence", "1. Evidence Governance"),
    ("alignment", "2. Semantic Alignment"),
    ("pci", "3. PCI / ProofChecker"),
    ("dim", "4. DIM Gate"),
    ("execute", "5. Execution"),
]

DEFENSE_LAYER_LABELS: Dict[str, str] = {
    "none": "Baseline — no Evidence Governance (intentional vulnerability)",
    "evidence_tier1": "Layer 1 — Tier 1: Heuristic Evidence (Differential Heuristics)",
    "evidence_tier2": "Layer 1 — Tier 2: Reconstructed Evidence (Bidirectional Reconstruction)",
    "evidence_tier3": "Layer 1 — Tier 3: Cryptographic Evidence (PCI evidence_hash)",
    "semantic_alignment": "Layer 2 — Semantic Alignment (proxy gaming detection)",
    "async_audit": "Layer 3 — Async Semantic Auditing (approval-rate drift)",
}

EVENT_STAGE: Dict[str, str] = {
    "EVIDENCE_ABORT": "evidence",
    "SEMANTIC_ALIGNMENT_ABORT": "alignment",
    "SEMANTIC_ALIGNMENT_FLAG": "alignment",
    "PCI_VERIFICATION": "pci",
    "CREDIT_DECISION": "dim",
    "CREDIT_LIMIT_RAISED": "execute",
}

EVENT_LABELS: Dict[str, str] = {
    "EVIDENCE_ABORT": "Evidence abort",
    "SEMANTIC_ALIGNMENT_ABORT": "Alignment abort",
    "SEMANTIC_ALIGNMENT_FLAG": "Alignment flag",
    "PCI_VERIFICATION": "PCI verification",
    "CREDIT_DECISION": "DIM verdict",
    "CREDIT_LIMIT_RAISED": "Limit raised",
    "MONITOR_TICK": "Monitor tick",
    "AGENT_SUSPENDED": "Agent suspended",
}


@dataclass
class StageStatus:
    status: str  # passed | blocked | warning | skipped | not_reached
    detail: str = ""


@dataclass
class ScenarioVerdict:
    headline: str
    css_class: str
    blocked_stage: Optional[str] = None


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _events_for_simulation(
    all_events: Sequence[Dict[str, Any]],
    simulation_id: str,
) -> List[Dict[str, Any]]:
    start_idx = None
    for i in range(len(all_events) - 1, -1, -1):
        e = all_events[i]
        if e.get("event") != "SIMULATION_START":
            continue
        d = e.get("details") or {}
        if d.get("simulation_id") == simulation_id:
            start_idx = i
            break
    if start_idx is None:
        return []
    out: List[Dict[str, Any]] = []
    for j in range(start_idx, len(all_events)):
        e = all_events[j]
        ev_name = e.get("event", "")
        if ev_name in ("SIMULATION_START", "SIMULATION_END"):
            continue
        out.append(e)
        if ev_name == "SIMULATION_END":
            d = e.get("details") or {}
            if d.get("simulation_id") == simulation_id:
                break
    return out


def _scenario_label_from_event(e: Dict[str, Any]) -> str:
    details = e.get("details") or {}
    label = details.get("scenario_label")
    if label:
        return str(label)
    cid = details.get("customer_id", "")
    if isinstance(cid, str) and cid.startswith("drift_cust_"):
        return f"drift_{cid.replace('drift_cust_', '')}"
    return ""


def _group_events_by_scenario(
    events: Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    dfid_to_label: Dict[str, str] = {}

    for e in events:
        label = _scenario_label_from_event(e)
        dfid = str(e.get("dfid", ""))
        if label:
            dfid_to_label[dfid] = label
        elif dfid in dfid_to_label:
            label = dfid_to_label[dfid]

        if not label:
            continue
        groups.setdefault(label, []).append(e)

    for label, evs in groups.items():
        groups[label] = sorted(evs, key=lambda x: str(x.get("created_at", "")))
    return groups


def _analyze_stages(
    events: List[Dict[str, Any]],
    *,
    skip_evidence: bool = False,
) -> Dict[str, StageStatus]:
    stages = {k: StageStatus("not_reached") for k, _ in PIPELINE_STAGES}

    if skip_evidence:
        stages["evidence"] = StageStatus("skipped", "Evidence Governance bypassed")
        stages["alignment"] = StageStatus("skipped", "Not evaluated")
        stages["pci"] = StageStatus("skipped", "No PCI — direct PolicyProposal")

    for e in events:
        ev = e.get("event", "")
        state = str(e.get("state", ""))
        details = e.get("details") or {}
        reason = str(details.get("reason", ""))

        if ev == "EVIDENCE_ABORT":
            stages["evidence"] = StageStatus("blocked", reason)
            return stages
        if ev == "SEMANTIC_ALIGNMENT_ABORT":
            if stages["evidence"].status == "not_reached":
                stages["evidence"] = StageStatus("passed", "Tiers 1+2 OK")
            stages["alignment"] = StageStatus("blocked", reason)
            return stages
        if ev == "SEMANTIC_ALIGNMENT_FLAG":
            if stages["evidence"].status == "not_reached":
                stages["evidence"] = StageStatus("passed", "Tiers 1+2 OK")
            stages["alignment"] = StageStatus("warning", f"{state}: {reason}")
        if ev == "PCI_VERIFICATION":
            if stages["evidence"].status == "not_reached":
                stages["evidence"] = StageStatus("passed", "Tiers 1+2 OK")
            if stages["alignment"].status == "not_reached":
                stages["alignment"] = StageStatus("passed", "No proxy gaming block")
            if state == "REJECT" or not details.get("proof_ok", True):
                stages["pci"] = StageStatus("blocked", reason or "Evidence Invalid")
                return stages
            stages["pci"] = StageStatus("passed", "ProofChecker OK")
        if ev == "CREDIT_DECISION":
            if stages["pci"].status == "not_reached" and not skip_evidence:
                stages["pci"] = StageStatus("passed", "ProofChecker OK")
            verdict = state
            if verdict == "ACCEPT" or "ACCEPT" in verdict:
                stages["dim"] = StageStatus("passed", str(details.get("reason", "VALIDATION_PASSED")))
            else:
                stages["dim"] = StageStatus("blocked", reason or verdict)
                return stages
        if ev == "CREDIT_LIMIT_RAISED":
            stages["execute"] = StageStatus(
                "passed",
                f"Limit {details.get('new_limit_pln')} PLN"
                + (" (high risk)" if details.get("high_risk") else ""),
            )

    if skip_evidence:
        for key in ("alignment", "pci"):
            if stages[key].status == "not_reached":
                stages[key] = StageStatus("skipped", "Bypassed")

    for key, st in stages.items():
        if st.status == "not_reached" and key != "execute":
            if key == "execute":
                stages[key] = StageStatus("not_reached", "Not executed")
            elif events and key in ("dim",) and stages.get("pci", StageStatus("")).status == "blocked":
                stages[key] = StageStatus("not_reached", "Not reached")
            elif not events:
                pass
            elif key == "execute" and stages["dim"].status != "passed":
                stages[key] = StageStatus("not_reached", "Blocked upstream")

    if stages["dim"].status == "passed" and stages["execute"].status == "not_reached":
        stages["execute"] = StageStatus("not_reached", "DIM accepted but no execution recorded")

    return stages


def _derive_verdict(
    stages: Dict[str, StageStatus],
    scenario: Optional[ScenarioConfig],
) -> ScenarioVerdict:
    for key, _label in PIPELINE_STAGES:
        st = stages[key]
        if st.status == "blocked":
            stage_name = dict(PIPELINE_STAGES)[key]
            return ScenarioVerdict(
                headline=f"BLOCKED at {stage_name}",
                css_class="verdict-blocked",
                blocked_stage=key,
            )
        if st.status == "warning" and key == "alignment":
            if stages["execute"].status == "passed":
                return ScenarioVerdict(
                    headline="EXECUTED with audit flag (NEEDS_REVIEW)",
                    css_class="verdict-warning",
                )

    if stages["execute"].status == "passed":
        if scenario and scenario.skip_evidence_governance:
            return ScenarioVerdict(
                headline="EXECUTED — catastrophic baseline (no Evidence Governance)",
                css_class="verdict-catastrophic",
            )
        return ScenarioVerdict(
            headline="PASSED — full pipeline executed",
            css_class="verdict-passed",
        )

    if scenario:
        expected = scenario.expected
        if expected == "EVIDENCE_ABORT" and stages["evidence"].status == "blocked":
            return ScenarioVerdict(
                headline="BLOCKED as expected — Compliant Lie caught",
                css_class="verdict-expected",
            )
        if expected == "ALIGNMENT_ABORT" and stages["alignment"].status == "blocked":
            return ScenarioVerdict(
                headline="BLOCKED as expected — proxy gaming (strict mode)",
                css_class="verdict-expected",
            )
        if expected == "PCI_REJECT" and stages["pci"].status == "blocked":
            return ScenarioVerdict(
                headline="BLOCKED as expected — tampered PCI",
                css_class="verdict-expected",
            )

    return ScenarioVerdict(
        headline="Completed — see pipeline stages",
        css_class="verdict-neutral",
    )


def _stage_chip(key: str, label: str, st: StageStatus) -> str:
    css = f"stage stage-{st.status}"
    icon = {
        "passed": "✓",
        "blocked": "✕",
        "warning": "⚠",
        "skipped": "—",
        "not_reached": "·",
    }.get(st.status, "?")
    detail = f'<span class="stage-detail">{_esc(st.detail)}</span>' if st.detail else ""
    return (
        f'<div class="{css}">'
        f'<div class="stage-icon">{icon}</div>'
        f'<div class="stage-name">{_esc(label)}</div>'
        f"{detail}"
        f"</div>"
    )


def _pipeline_html(stages: Dict[str, StageStatus]) -> str:
    chips = [_stage_chip(k, lbl, stages[k]) for k, lbl in PIPELINE_STAGES]
    return f'<div class="pipeline">{"".join(chips)}</div>'


def _truncate(text: str, max_len: int = 96) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _is_failure_event(e: Dict[str, Any]) -> bool:
    ev = str(e.get("event", ""))
    state = str(e.get("state", "")).upper()
    details = e.get("details") or {}
    if ev in (
        "EVIDENCE_ABORT",
        "SEMANTIC_ALIGNMENT_ABORT",
        "AGENT_SUSPENDED",
    ):
        return True
    if ev == "PCI_VERIFICATION" and (
        state == "REJECT" or not details.get("proof_ok", True)
    ):
        return True
    if ev == "CREDIT_DECISION" and state and "ACCEPT" not in state:
        return True
    if state in ("ABORT", "REJECT", "ALERT", "SUSPENDED"):
        return True
    return False


def _event_summary_line(e: Dict[str, Any]) -> str:
    ev = str(e.get("event", ""))
    state = str(e.get("state", ""))
    details = e.get("details") or {}

    if ev == "EVIDENCE_ABORT":
        return str(details.get("reason", "Evidence abort"))
    if ev in ("SEMANTIC_ALIGNMENT_ABORT", "SEMANTIC_ALIGNMENT_FLAG"):
        flag = details.get("flag", state)
        reason = details.get("reason", "")
        return f"{flag}: {reason}" if reason else str(flag)
    if ev == "PCI_VERIFICATION":
        ok = details.get("proof_ok", state == "OK")
        return str(details.get("reason", "OK" if ok else "Evidence Invalid"))
    if ev == "CREDIT_DECISION":
        return f"{details.get('verdict', state)} — {details.get('reason', '')}"
    if ev == "CREDIT_LIMIT_RAISED":
        limit = details.get("new_limit_pln", "?")
        risk = "high risk" if details.get("high_risk") else "low risk"
        return f"Limit {limit} PLN ({risk})"
    if ev == "MONITOR_TICK":
        rate = details.get("high_risk_approval_rate")
        if rate is not None:
            return (
                f"Rolling high-risk rate {float(rate) * 100:.0f}% "
                f"(threshold {float(details.get('threshold', 0)) * 100:.0f}%)"
            )
        return state
    if ev == "AGENT_SUSPENDED":
        rate = details.get("high_risk_approval_rate")
        reason = details.get("reason", "")
        if rate is not None:
            return f"{reason} at {float(rate) * 100:.0f}% high-risk rate"
        return str(reason or "Agent suspended")
    if details.get("reason"):
        return str(details["reason"])
    if details.get("verdict"):
        return str(details["verdict"])
    return state or ev


def _event_details_cell(details: Dict[str, Any]) -> str:
    raw = json.dumps(details, indent=2, default=str)
    return (
        '<details class="json-details">'
        '<summary>Full JSON</summary>'
        f'<pre class="event-detail">{_esc(raw)}</pre>'
        "</details>"
    )


def _event_rows(events: List[Dict[str, Any]]) -> str:
    if not events:
        return '<p class="muted">No audit events for this scenario.</p>'
    rows = []
    for e in events:
        ev = e.get("event", "")
        details = e.get("details") or {}
        stage = EVENT_STAGE.get(ev, "")
        stage_lbl = dict(PIPELINE_STAGES).get(stage, "—")
        friendly = EVENT_LABELS.get(ev, ev)
        row_cls = "row-failure" if _is_failure_event(e) else ""
        summary = _truncate(_event_summary_line(e), 120)
        rows.append(
            f"<tr class='{row_cls}'>"
            f"<td><code>{_esc(str(e.get('dfid', ''))[:12])}</code></td>"
            f"<td>{_esc(stage_lbl)}</td>"
            f"<td><strong>{_esc(friendly)}</strong></td>"
            f"<td>{_esc(e.get('state', ''))}</td>"
            f"<td class='event-summary'>{_esc(summary)}</td>"
            f"<td>{_event_details_cell(details)}</td>"
            "</tr>"
        )
    return (
        "<table class='event-table'><thead><tr>"
        "<th>DFID</th><th>Stage</th><th>Event</th><th>State</th>"
        "<th>Summary</th><th>Raw payload</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _key_reason_from_stages(
    stages: Dict[str, StageStatus],
    verdict: ScenarioVerdict,
) -> str:
    for key, _lbl in PIPELINE_STAGES:
        st = stages[key]
        if st.status == "blocked" and st.detail:
            return _truncate(st.detail, 96)
        if st.status == "warning" and st.detail:
            return _truncate(st.detail, 96)
    if verdict.css_class == "verdict-catastrophic":
        return "Evidence Governance bypassed — structurally valid lie executed"
    if verdict.css_class == "verdict-passed":
        return "All pipeline stages passed"
    if verdict.css_class == "verdict-warning":
        return "Executed with NEEDS_REVIEW audit flag"
    return "—"


def _scenario_section(
    scenario: ScenarioConfig,
    events: List[Dict[str, Any]],
) -> str:
    layer_lbl = DEFENSE_LAYER_LABELS.get(
        scenario.defense_layer,
        scenario.defense_layer,
    )
    stages = _analyze_stages(events, skip_evidence=scenario.skip_evidence_governance)
    verdict = _derive_verdict(stages, scenario)

    claim_preview = json.dumps(scenario.claim, indent=2)
    chat_preview = scenario.chat_transcript.replace("\n", " ").strip()

    return f"""
<section class="scenario-card" id="{_esc(scenario.label)}">
  <header class="scenario-header">
    <div class="scenario-title">
      <span class="scenario-id">{_esc(scenario.label)}</span>
      <span class="expected-badge">expected: {_esc(scenario.expected)}</span>
    </div>
    <h3 class="layer-title">{_esc(layer_lbl)}</h3>
    <p class="purpose">{_esc(scenario.notes)}</p>
    <div class="verdict-banner {verdict.css_class}">{_esc(verdict.headline)}</div>
  </header>

  <div class="fixture-box">
    <h4>Test fixture</h4>
    <p><strong>Chat:</strong> {_esc(chat_preview)}</p>
    <p><strong>Claim:</strong></p>
    <pre class="fixture-pre">{_esc(claim_preview)}</pre>
    <p><strong>Justification:</strong> {_esc(scenario.justification[:300])}</p>
  </div>

  {_pipeline_html(stages)}

  <details class="event-log">
    <summary>Audit event log ({len(events)} events)</summary>
    {_event_rows(events)}
  </details>
</section>
"""


def _window_strip_html(
    flags: Sequence[bool],
    labels: Sequence[str],
    *,
    window_size: int,
    warming: bool,
) -> str:
    """Visual rolling window: L=low risk, H=high risk, ·=slot not yet filled."""
    cells: List[str] = []
    display_len = window_size if not warming else window_size
    for i in range(display_len):
        if i < len(flags):
            high = flags[i]
            lbl = labels[i] if i < len(labels) else f"#{i + 1}"
            css = "wcell-high" if high else "wcell-low"
            if i == len(flags) - 1:
                css += " wcell-current"
            sym = "H" if high else "L"
            cells.append(
                f'<span class="wcell {css}" title="{_esc(lbl)}">{sym}</span>'
            )
        else:
            cells.append('<span class="wcell wcell-pending" title="pending">·</span>')
    return f'<div class="drift-window">{"".join(cells)}</div>'


def _drift_accumulation_table(
    events: Sequence[Dict[str, Any]],
    *,
    window_size: int,
    threshold: float,
    phase1_iterations: int,
    monitor_events: Sequence[Dict[str, Any]],
) -> str:
    raises = sorted(
        [
            e
            for e in events
            if e.get("event") == "CREDIT_LIMIT_RAISED"
            and is_drift_batch_execution(e.get("details") or {})
        ],
        key=lambda x: str(x.get("created_at", "")),
    )

    suspended_dfids = {
        str(e.get("dfid", ""))
        for e in monitor_events
        if e.get("event") == "AGENT_SUSPENDED"
    }

    all_flags: List[bool] = []
    all_labels: List[str] = []
    rows: List[str] = []

    for seq, e in enumerate(raises, 1):
        details = e.get("details") or {}
        label = str(details.get("scenario_label", f"drift_{seq:02d}"))
        iter_num = (
            int(label.split("_")[-1])
            if label.split("_")[-1].isdigit()
            else seq
        )
        phase = (
            "Drift batch Phase 1 — legit ratio"
            if iter_num <= phase1_iterations
            else "Drift batch Phase 2 — marginal income"
        )
        income = details.get("declared_income_pln")
        limit = details.get("new_limit_pln")
        income_s = f"{int(income)}" if income is not None else "—"
        limit_s = f"{int(limit)}" if limit is not None else "—"
        high_risk = bool(details.get("high_risk", False))
        dfid = str(e.get("dfid", ""))

        all_flags.append(high_risk)
        all_labels.append(label)

        warming = len(all_flags) < window_size
        if warming:
            win_flags = all_flags
            win_labels = all_labels
            hi_count = sum(all_flags)
            rate_cell = f"warming ({len(all_flags)}/{window_size})"
            count_cell = f"{hi_count}/{len(all_flags)} in history"
            status = "ACCUMULATING"
            row_cls = ""
        else:
            win_flags = all_flags[-window_size:]
            win_labels = all_labels[-window_size:]
            hi_count = sum(win_flags)
            rate = hi_count / float(window_size)
            rate_cell = f"{rate * 100:.0f}% (threshold {threshold * 100:.0f}%)"
            count_cell = f"{hi_count}/{window_size} high in window"
            if dfid in suspended_dfids:
                status = "SUSPENDED"
                row_cls = "row-failure"
            elif rate > threshold + 1e-12:
                status = "ALERT"
                row_cls = "row-warning"
            else:
                status = "OK"
                row_cls = ""

        strip = _window_strip_html(
            win_flags,
            win_labels,
            window_size=window_size,
            warming=warming,
        )
        risk_badge = (
            '<span class="risk-badge risk-high">HIGH</span>'
            if high_risk
            else '<span class="risk-badge risk-low">low</span>'
        )

        rows.append(
            f"<tr class='{row_cls}'>"
            f"<td>{seq}</td>"
            f"<td><code>{_esc(label)}</code></td>"
            f"<td>{_esc(phase)}</td>"
            f"<td>{_esc(income_s)}</td>"
            f"<td>{_esc(limit_s)}</td>"
            f"<td>{risk_badge}</td>"
            f"<td>{strip}</td>"
            f"<td>{_esc(count_cell)}</td>"
            f"<td>{_esc(rate_cell)}</td>"
            f"<td><strong>{_esc(status)}</strong></td>"
            "</tr>"
        )

    if not rows:
        return '<p class="muted">No drift-batch iterations recorded.</p>'

    legend = (
        '<p class="drift-legend">'
        "<strong>Rolling window</strong> (last "
        f"{window_size} drift approvals only — Phase A executions are excluded): "
        '<span class="wcell wcell-low inline">L</span> low-risk approval, '
        '<span class="wcell wcell-high inline">H</span> high-risk approval, '
        '<span class="wcell wcell-pending inline">·</span> slot not yet filled. '
        "Highlighted cell = approval just added in this row."
        "</p>"
    )

    return (
        legend
        + "<table class='drift-trend-table'><thead><tr>"
        "<th>#</th><th>Iteration</th><th>Drift batch phase</th>"
        "<th>Income</th><th>Limit</th><th>This approval</th>"
        "<th>Rolling window state</th>"
        "<th>High-risk in window</th><th>Rolling rate</th><th>Monitor</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _drift_section(
    events: Sequence[Dict[str, Any]],
    monitor_events: List[Dict[str, Any]],
    *,
    window_size: int,
    threshold: float,
    phase1_iterations: int,
) -> str:
    trend_html = _drift_accumulation_table(
        events,
        window_size=window_size,
        threshold=threshold,
        phase1_iterations=phase1_iterations,
        monitor_events=monitor_events,
    )
    monitor_html = _event_rows(monitor_events) if monitor_events else ""

    suspended = any(e.get("event") == "AGENT_SUSPENDED" for e in monitor_events)
    outcome_banner = ""
    if suspended:
        for e in monitor_events:
            if e.get("event") == "AGENT_SUSPENDED":
                details = e.get("details") or {}
                rate = details.get("high_risk_approval_rate")
                pct = f"{float(rate) * 100:.0f}%" if rate is not None else "?"
                outcome_banner = (
                    f'<div class="verdict-banner verdict-blocked">'
                    f"Agent SUSPENDED — rolling high-risk approval rate {pct} "
                    f"exceeded {threshold * 100:.0f}% threshold "
                    f"(window size {window_size})</div>"
                )
                break

    return f"""
<section class="phase-section" id="phase-b-drift">
  <h2>Phase B — Drift Batch (Layer 3: Async Semantic Auditing)</h2>
  <p class="purpose term-xref">
    <em>Terminology: see legend above.</em> After Phase A, the sample runs a batch of
    similar limit-raise requests with a social-engineering phrase.
    <strong>Drift batch Phase 1</strong> ({phase1_iterations} iterations) uses comfortable
    income/limit ratios (low risk). <strong>Drift batch Phase 2</strong> switches to
    marginal income (high risk). The async monitor keeps only the last
    <strong>{window_size}</strong> drift-batch approvals in a rolling window and
    suspends the agent when high-risk share exceeds <strong>{threshold * 100:.0f}%</strong>.
  </p>
  {outcome_banner}

  <h3>Accumulating approval history</h3>
  {trend_html}

  <details class="event-log">
    <summary>Monitor event log ({len(monitor_events)} events)</summary>
    {monitor_html}
  </details>
</section>
"""


def _terminology_legend_html(sample_dir: Path) -> str:
    config = load_yaml_config(sample_dir / "config.yaml")
    drift_raw = config.get("drift_batch") or {}
    phase1_iters = int(drift_raw.get("phase1_iterations", 5))

    doc_topologies = "../../../docs/03-topologies/DIR_Topologies.md"
    doc_readme = "../README.md"
    doc_sample12 = "../../12_compliant_lie/README.md"

    return f"""
<details class="terminology-legend" open>
  <summary>How to read this report — terminology &amp; sources</summary>

  <div class="term-body">
    <h3 class="term-heading">Source documents</h3>
    <ul class="term-sources">
      <li>
        <a href="{_esc(doc_topologies)}">DIR Topologies</a>
        — §8 The Evidence Governance Layer &amp; The Compliant Lie;
        §8.2.1 Evidence Hierarchy (Tiers 1–3); §8.4 defense-in-depth table (Layers 1–3).
      </li>
      <li>
        <a href="{_esc(doc_readme)}">39_fintech_evidence_governance README</a>
        — sample goals, Topology C (DL+PCI), scenario list, configuration.
      </li>
      <li>
        <a href="{_esc(doc_sample12)}">12_compliant_lie README</a>
        — minimal Layer 1 (Evidence Governance) reference sample.
      </li>
    </ul>

    <h3 class="term-heading">Concept hierarchy</h3>
    <p class="term-intro">
      This report uses <strong>three naming schemes</strong>. They nest as follows
      (DIR architecture vs. this sample&apos;s report structure):
    </p>
    <pre class="term-tree">Report structure (this sample only)
├── Phase A — fixed YAML scenarios (scenarios.yaml)
│   ├── Layer 1 — Evidence Governance  →  Tier 1 / Tier 2 / Tier 3
│   ├── Layer 2 — Semantic Alignment
│   └── baseline (no Layer 1 — intentional vulnerability)
└── Phase B — drift batch loop (run.py)
    └── Layer 3 — Async Semantic Auditing
        └── Drift batch Phase 1 / Phase 2  (income profile — not Phase A/B)</pre>

    <p class="term-note">
      <strong>Do not confuse:</strong> <em>Phase A / Phase B</em> are sections of this
      HTML report. <em>Drift batch Phase 1 / Phase 2</em> are income phases inside
      Phase B only (configured in <code>drift_batch.phase1_iterations</code>).
    </p>

    <h3 class="term-heading">§8.4 defense layers (DIR architecture)</h3>
    <dl class="term-dl">
      <dt>Layer 1 — Evidence Governance</dt>
      <dd>
        User Space, <em>before</em> PCI signing. Catches a single
        <strong>Compliant Lie</strong> (structurally valid, semantically wrong claim).
        Blocking — no evidence package, no signed artifact. See DIR Topologies §8.2–§8.3.
        In Phase A: scenarios <code>1_*</code>–<code>4_*</code>;
        <code>0_baseline_no_evidence</code> deliberately skips this layer.
      </dd>
      <dt>Layer 2 — Semantic Alignment</dt>
      <dd>
        DIM-adjacent soft guard at validation time. Targets <strong>proxy gaming</strong>
        (narrative does not match policy mission). Audit mode flags <code>NEEDS_REVIEW</code>;
        strict mode aborts. See §8.4 table. In Phase A: scenarios <code>5_*</code>,
        <code>6_*</code>.
      </dd>
      <dt>Layer 3 — Async Semantic Auditing</dt>
      <dd>
        Post-execution rolling monitor (off the critical path). Detects
        <strong>semantic drift</strong> over many approvals — the &quot;Day Three&quot; problem.
        Non-blocking per decision; triggers <code>SUSPENDED</code> on aggregate threshold breach.
        See §8.4 table. Demonstrated entirely in <strong>Phase B</strong> of this report.
      </dd>
    </dl>

    <h3 class="term-heading">Evidence tiers (within Layer 1 only)</h3>
    <p class="term-intro">
      Tiers are levels of the <strong>Evidence Hierarchy</strong> (§8.2.1). All three belong
      to Layer 1; they are <em>not</em> the same as Layers 1–3.
    </p>
    <dl class="term-dl">
      <dt>Tier 1 — Heuristic Evidence</dt>
      <dd>
        Deterministic checks (regex, rules) vs. the LLM claim — Differential Heuristics
        (§8.3 Pattern 1). Module: <code>evidence.py</code>.
        Scenario: <code>1_heuristic_compliant_lie</code>.
      </dd>
      <dt>Tier 2 — Reconstructed Evidence</dt>
      <dd>
        Independent reconstruction of context from the claim — Bidirectional Reconstruction
        (§8.3 Pattern 2). Scenario: <code>2_reconstruction_compliant_lie</code>.
      </dd>
      <dt>Tier 3 — Cryptographic Evidence</dt>
      <dd>
        Signed PCI with <code>evidence_hash</code>; verified by ProofChecker in Kernel Space
        (Topology C). Scenarios: <code>3_honest_pci</code>, <code>4_tampered_pci</code>.
      </dd>
    </dl>

    <h3 class="term-heading">Report phases (this sample only — not DIR terms)</h3>
    <dl class="term-dl">
      <dt>Phase A — YAML defense scenarios</dt>
      <dd>
        Seven fixed test cases from <code>scenarios.yaml</code>. Each card isolates one
        defense mechanism (or the baseline vulnerability). Shown in the Executive summary
        and scenario cards below.
      </dd>
      <dt>Phase B — Drift batch</dt>
      <dd>
        Automated loop (~20 iterations) after Phase A. Same pipeline per request, but the
        goal is to show Layer 3 accumulation: marginal approvals raise the rolling
        high-risk rate until the agent is suspended.
      </dd>
      <dt>Drift batch Phase 1 / Phase 2</dt>
      <dd>
        Income profile inside Phase B only. Phase 1 (first {phase1_iters} iterations):
        comfortable income/limit ratio → <code>low</code> risk badge.
        Phase 2: marginal income → <code>HIGH</code> risk; rolling window fills with
        <span class="wcell wcell-high inline">H</span> cells.
      </dd>
    </dl>

    <h3 class="term-heading">Pipeline strip (per scenario card)</h3>
    <p class="term-intro">
      The five-stage strip on each card is the <strong>runtime path for one decision</strong>.
      It is related to but not identical to Layers 1–3:
    </p>
    <ol class="term-ol">
      <li><strong>Evidence Governance</strong> — Layer 1 gates (Tiers 1–2 in User Space)</li>
      <li><strong>Semantic Alignment</strong> — Layer 2</li>
      <li><strong>PCI / ProofChecker</strong> — Tier 3 cryptographic check (Kernel)</li>
      <li><strong>DIM Gate</strong> — contract validation (Kernel)</li>
      <li><strong>Execution</strong> — mock limit raise; feeds Layer 3 monitor in Phase B</li>
    </ol>

    <h3 class="term-heading">Quick map</h3>
    <table class="term-map-table">
      <thead>
        <tr><th>Report label</th><th>Means</th><th>Example</th></tr>
      </thead>
      <tbody>
        <tr>
          <td><code>Layer 1 — Tier 1</code></td>
          <td>Heuristic evidence gate</td>
          <td><code>1_heuristic_compliant_lie</code></td>
        </tr>
        <tr>
          <td><code>Layer 2 — Semantic Alignment</code></td>
          <td>Proxy gaming check</td>
          <td><code>5_proxy_gaming_audit</code></td>
        </tr>
        <tr>
          <td><code>Phase B — Drift batch Phase 2</code></td>
          <td>Marginal-income drift iteration</td>
          <td><code>drift_06</code> onward</td>
        </tr>
        <tr>
          <td><code>ACCUMULATING</code></td>
          <td>Rolling window not yet full</td>
          <td>Drift rows 1–9 (window size 10)</td>
        </tr>
        <tr>
          <td><code>L</code> / <code>H</code> / <code>·</code></td>
          <td>Low-risk / high-risk / empty window slot</td>
          <td>Rolling window state column in Phase B</td>
        </tr>
      </tbody>
    </table>
  </div>
</details>
"""


def _summary_table(scenarios: List[ScenarioConfig], groups: Dict[str, List[Dict[str, Any]]]) -> str:
    rows = []
    for sc in scenarios:
        evs = groups.get(sc.label, [])
        stages = _analyze_stages(evs, skip_evidence=sc.skip_evidence_governance)
        verdict = _derive_verdict(stages, sc)
        key_reason = _key_reason_from_stages(stages, verdict)
        rows.append(
            "<tr>"
            f"<td><a href='#{_esc(sc.label)}'>{_esc(sc.label)}</a></td>"
            f"<td>{_esc(DEFENSE_LAYER_LABELS.get(sc.defense_layer, sc.defense_layer))}</td>"
            f"<td class='{verdict.css_class}'>{_esc(verdict.headline)}</td>"
            f"<td class='key-reason'>{_esc(key_reason)}</td>"
            f"<td>{_esc(sc.expected)}</td>"
            "</tr>"
        )
    return (
        "<table class='summary-table'><thead><tr>"
        "<th>Scenario</th><th>Defense layer</th><th>Outcome</th>"
        "<th>Key reason</th><th>Expected</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


_REPORT_CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; background: #f5f5f5; color: #212121; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.subtitle { color: #616161; margin-bottom: 2rem; }
.phase-section { margin: 2.5rem 0; }
.phase-section > h2 {
  font-size: 1.25rem; border-bottom: 3px solid #3F51B5; padding-bottom: 0.5rem;
  margin-bottom: 1rem; color: #1A237E;
}
.scenario-card {
  background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
  margin-bottom: 2rem; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
.scenario-header {
  padding: 1.25rem 1.5rem; background: linear-gradient(135deg, #E8EAF6 0%, #fff 100%);
  border-bottom: 1px solid #e0e0e0;
}
.scenario-title { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
.scenario-id { font-family: monospace; font-size: 1.1rem; font-weight: 700; color: #1A237E; }
.expected-badge {
  font-size: 0.75rem; background: #E3F2FD; color: #1565C0; padding: 2px 8px; border-radius: 4px;
}
.layer-title { font-size: 0.95rem; color: #3949AB; margin: 0.5rem 0; font-weight: 600; }
.purpose { color: #555; margin: 0.5rem 0 1rem; line-height: 1.5; }
.verdict-banner {
  font-weight: 600; padding: 0.6rem 1rem; border-radius: 6px; margin-top: 0.75rem;
}
.verdict-banner.mini { font-size: 0.85rem; padding: 0.4rem 0.75rem; }
.verdict-blocked { background: #FFEBEE; color: #B71C1C; border-left: 4px solid #C62828; }
.verdict-passed { background: #E8F5E9; color: #1B5E20; border-left: 4px solid #388E3C; }
.verdict-warning { background: #FFF8E1; color: #E65100; border-left: 4px solid #FF9800; }
.verdict-catastrophic { background: #FCE4EC; color: #880E4F; border-left: 4px solid #AD1457; }
.verdict-expected { background: #E0F2F1; color: #00695C; border-left: 4px solid #00897B; }
.verdict-neutral { background: #ECEFF1; color: #37474F; border-left: 4px solid #78909C; }
.fixture-box { padding: 1rem 1.5rem; background: #FAFAFA; border-bottom: 1px solid #eee; font-size: 0.9rem; }
.fixture-box h4 { margin: 0 0 0.5rem; font-size: 0.8rem; text-transform: uppercase; color: #757575; }
.fixture-pre { font-size: 0.8rem; background: #fff; border: 1px solid #e0e0e0; padding: 0.5rem; overflow-x: auto; }
.pipeline {
  display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 1.25rem 1.5rem;
  background: #fff;
}
.stage {
  flex: 1; min-width: 140px; padding: 0.75rem; border-radius: 6px; text-align: center;
  border: 2px solid #e0e0e0; font-size: 0.8rem;
}
.stage-passed { border-color: #66BB6A; background: #F1F8E9; }
.stage-blocked { border-color: #EF5350; background: #FFEBEE; }
.stage-warning { border-color: #FFA726; background: #FFF8E1; }
.stage-skipped { border-color: #BDBDBD; background: #F5F5F5; color: #757575; }
.stage-not_reached { border-color: #E0E0E0; background: #FAFAFA; color: #9E9E9E; }
.stage-icon { font-size: 1.2rem; font-weight: bold; margin-bottom: 0.25rem; }
.stage-name { font-weight: 600; margin-bottom: 0.25rem; }
.stage-detail { display: block; font-size: 0.7rem; color: #616161; margin-top: 0.25rem; word-break: break-word; }
.event-log { padding: 0 1.5rem 1.25rem; }
.event-log summary { cursor: pointer; font-weight: 600; color: #3949AB; padding: 0.5rem 0; }
.event-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 0.5rem; }
.event-table th, .event-table td { border: 1px solid #e0e0e0; padding: 6px 8px; vertical-align: top; }
.event-table th { background: #E8EAF6; text-align: left; }
.event-detail { font-size: 0.7rem; margin: 0.25rem 0 0; max-height: 160px; overflow: auto; }
.event-summary { font-size: 0.82rem; line-height: 1.4; max-width: 280px; }
.json-details summary { cursor: pointer; font-size: 0.72rem; color: #5C6BC0; }
.event-table tr.row-failure { background: #FFEBEE; }
.event-table tr.row-failure td { border-color: #FFCDD2; }
.event-table tr.row-warning { background: #FFF8E1; }
.summary-table { width: 100%; border-collapse: collapse; margin: 1rem 0 2rem; background: #fff; }
.summary-table th, .summary-table td { border: 1px solid #e0e0e0; padding: 8px 10px; text-align: left; vertical-align: top; }
.summary-table th { background: #E8F5E9; }
.summary-table .key-reason { font-size: 0.85rem; color: #424242; max-width: 320px; }
.muted { color: #9E9E9E; font-style: italic; }
.drift-trend-table { width: 100%; border-collapse: collapse; margin: 1rem 0 1.5rem; background: #fff; }
.drift-trend-table th, .drift-trend-table td { border: 1px solid #e0e0e0; padding: 8px 10px; text-align: left; }
.drift-trend-table th { background: #FFF3E0; }
.drift-trend-table tr.row-failure { background: #FFEBEE; }
.drift-trend-table tr.row-warning { background: #FFF8E1; }
.drift-legend { font-size: 0.85rem; color: #555; margin: 0 0 1rem; line-height: 1.6; }
.drift-window { display: flex; gap: 3px; flex-wrap: nowrap; }
.wcell {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 4px; font-size: 0.65rem; font-weight: 700;
  border: 1px solid #bdbdbd;
}
.wcell.inline { width: 18px; height: 18px; vertical-align: middle; }
.wcell-low { background: #E8F5E9; color: #2E7D32; border-color: #81C784; }
.wcell-high { background: #FFEBEE; color: #C62828; border-color: #E57373; }
.wcell-pending { background: #F5F5F5; color: #BDBDBD; border-style: dashed; }
.wcell-current { box-shadow: 0 0 0 2px #3F51B5; }
.risk-badge { font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
.risk-low { background: #E8F5E9; color: #2E7D32; }
.risk-high { background: #FFEBEE; color: #C62828; }
.terminology-legend {
  background: #fff; border: 1px solid #c5cae9; border-radius: 8px;
  margin: 0 0 2rem; padding: 0 1.25rem 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.terminology-legend summary {
  cursor: pointer; font-weight: 700; color: #1A237E; padding: 1rem 0;
  font-size: 1rem; list-style-position: outside;
}
.term-body { font-size: 0.88rem; line-height: 1.55; color: #424242; }
.term-heading {
  font-size: 0.95rem; color: #3949AB; margin: 1.25rem 0 0.5rem;
  border-bottom: 1px solid #e8eaf6; padding-bottom: 0.25rem;
}
.term-heading:first-child { margin-top: 0; }
.term-intro { margin: 0.35rem 0 0.75rem; }
.term-sources { margin: 0.25rem 0 0.5rem 1.25rem; padding: 0; }
.term-sources a { color: #1565C0; }
.term-tree {
  font-family: Consolas, monospace; font-size: 0.78rem; background: #f5f5f5;
  border: 1px solid #e0e0e0; padding: 0.75rem 1rem; overflow-x: auto;
  line-height: 1.45; margin: 0.5rem 0 1rem;
}
.term-note {
  background: #FFF8E1; border-left: 4px solid #FF9800; padding: 0.6rem 0.85rem;
  margin: 0.75rem 0; font-size: 0.85rem; color: #5d4037;
}
.term-dl { margin: 0.25rem 0 0.5rem; }
.term-dl dt { font-weight: 700; color: #1A237E; margin-top: 0.65rem; }
.term-dl dd { margin: 0.2rem 0 0 0; padding-left: 0.5rem; }
.term-ol { margin: 0.25rem 0 0.75rem 1.25rem; padding: 0; }
.term-ol li { margin-bottom: 0.35rem; }
.term-map-table {
  width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.82rem;
  background: #fafafa;
}
.term-map-table th, .term-map-table td {
  border: 1px solid #e0e0e0; padding: 6px 8px; text-align: left; vertical-align: top;
}
.term-map-table th { background: #E8EAF6; }
.term-xref { font-size: 0.88rem; }
.subtitle { margin-bottom: 1rem; }
"""


def generate_report(
    bundle: StorageBundle,
    *,
    simulation_id: str,
    sample_dir: Path,
) -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_path = results_dir / f"evidence_governance_{stamp}.html"

    events = _events_for_simulation(
        bundle.decision_audit.all_events_chronological(),
        simulation_id,
    )
    groups = _group_events_by_scenario(events)

    yaml_scenarios = load_scenarios(sample_dir / "scenarios.yaml")
    phase_a_html = []
    for sc in yaml_scenarios:
        phase_a_html.append(_scenario_section(sc, groups.get(sc.label, [])))

    config = load_yaml_config(sample_dir / "config.yaml")
    monitor_raw = config.get("approval_monitor") or {}
    drift_raw = config.get("drift_batch") or {}
    window_size = int(monitor_raw.get("window_size", 10))
    threshold = float(monitor_raw.get("high_risk_approval_rate_threshold", 0.35))
    phase1_iterations = int(drift_raw.get("phase1_iterations", 5))

    monitor_events = [
        e
        for e in events
        if e.get("event") in ("MONITOR_TICK", "AGENT_SUSPENDED")
    ]
    monitor_events = sorted(monitor_events, key=lambda x: str(x.get("created_at", "")))

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>39 Fintech Evidence Governance — Defense Report</title>
  <style>{_REPORT_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>39_fintech_evidence_governance — Semantic Defense Report</h1>
  <p class="subtitle">
    Simulation <code>{_esc(simulation_id)}</code> —
    generated {_esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}
  </p>

  {_terminology_legend_html(sample_dir)}

  <section class="phase-section">
    <h2>Executive summary</h2>
    <p class="purpose">
      Each scenario tests one layer of DIR Topologies §8.4 defense-in-depth
      (<em>terminology: see legend above</em>).
      The <strong>pipeline strip</strong> shows which stage passed, blocked, or was skipped.
      A red stage is where the decision was stopped.
    </p>
    {_summary_table(yaml_scenarios, groups)}
  </section>

  <section class="phase-section" id="phase-a">
    <h2>Phase A — YAML Defense Scenarios</h2>
    <p class="purpose term-xref">
      <em>Terminology: see legend above.</em>
      Seven fixed scenarios demonstrating Layer 1 (Evidence), Layer 2 (Semantic Alignment),
      and intentional baseline vulnerability.
    </p>
    {"".join(phase_a_html)}
  </section>

  {_drift_section(events, monitor_events, window_size=window_size, threshold=threshold, phase1_iterations=phase1_iterations)}
</div>
</body>
</html>
"""

    out_path.write_text(body, encoding="utf-8")
    return out_path
