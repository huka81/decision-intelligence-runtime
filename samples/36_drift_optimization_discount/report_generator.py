"""
HTML report: discount drift, rolling average, suspension, decision history, user reasons.

Data source: ``StorageBundle.decision_audit`` (regenerable offline via ``__main__``).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
_SAMPLE_DIR = Path(__file__).resolve().parent
for _p in (_SRC, _SAMPLES, _SAMPLE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core import AgentRegistry, ContextStore
from dir_core.storage import StorageBundle

from pipeline import SimulationResult, SimulationStep, moving_average_series


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _new_report_path(sample_dir: Path, slug: str = "retention_drift") -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    suffix = f"_{slug}" if slug else ""
    return results_dir / f"report_{stamp}{suffix}.html"


def _count_events_for_simulation(
    events: List[Dict[str, Any]], simulation_id: str
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for e in events:
        d = e.get("details") or {}
        if d.get("simulation_id") != simulation_id:
            continue
        ev = str(e.get("event") or "")
        counts[ev] = counts.get(ev, 0) + 1
    return counts


def _run_elapsed_seconds(
    events: List[Dict[str, Any]], simulation_id: str
) -> Optional[float]:
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    for e in events:
        d = e.get("details") or {}
        if d.get("simulation_id") != simulation_id:
            continue
        if e.get("event") == "SIMULATION_START":
            start_ts = str(e.get("timestamp") or "")
        if e.get("event") == "SIMULATION_END":
            end_ts = str(e.get("timestamp") or "")
    if not start_ts or not end_ts:
        return None
    try:
        t0 = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        return max(0.0, (t1 - t0).total_seconds())
    except (TypeError, ValueError):
        return None


def _self_check_passed(step: SimulationStep) -> Tuple[str, str]:
    if step.dim_verdict == "ROA_FAIL":
        return "no", step.dim_reason or "self_check_or_parse"
    if step.dim_verdict in ("ACCEPT", "REJECT") and step.dim_reason:
        return "yes", ""
    return "yes", ""


def _section5_roa_audit_blocks(sim: SimulationResult, agent_id: str) -> str:
    """§17.4 Section 5 — full ROA + DIM + execution reconstruction."""
    parts: List[str] = ['<div class="panel roa-audit">']
    parts.append("<h2>ROA decision cycle reconstruction</h2>")
    parts.append(
        '<p class="muted">Rebuilt from canonical <code>AGENT_DECISION</code> and '
        "related audit rows for this run.</p>"
    )
    if not sim.steps:
        parts.append('<p class="muted">No decision steps for this simulation_id.</p>')
        parts.append("</div>")
        return "\n".join(parts)

    for s in sim.steps:
        sc_pass, sc_reason = _self_check_passed(s)
        exec_yes = "yes" if s.executed else "no"
        proposed_action = (
            "retention_discount" if s.dim_verdict != "ROA_FAIL" else "(no proposal)"
        )
        side = (
            f"retention discount {s.discount_offered:.2f}% recorded (RETENTION_EXECUTED)"
            if s.executed
            else ("blocked" if s.dim_verdict == "REJECT" else "not executed")
        )
        block = f"""
<details class="roa-block">
  <summary>Iteration {s.iteration + 1} — <code>{_esc(s.dfid)}</code> — DIM {_esc(s.dim_verdict)}</summary>
  <pre class="reason">
DFID: {_esc(s.dfid)}
Agent: {_esc(agent_id)}  Role: EXECUTOR  Scope: retention_discount

[EXPLAIN]
  Narrative:   {_esc(s.explain_narrative or "(not recorded)")}

[POLICY]
  Proposed action:  {_esc(proposed_action)}
  Confidence:       (see AGENT_DECISION row in audit if recorded)
  Justification:    {_esc(s.justification or "(not recorded)")}

[SELF-CHECK]
  Passed: {sc_pass}
  Reason (if failed): {_esc(sc_reason or "(n/a)")}

[DIM VALIDATION]
  Verdict:  {_esc(s.dim_verdict)}
  Reason:   {_esc(s.dim_reason or "(not recorded)")}

[EXECUTION]
  Executed: {exec_yes}
  Side effect: {_esc(side)}
  </pre>
</details>
"""
        parts.append(block)
    parts.append("</div>")
    return "\n".join(parts)


def _section7_kernel_html(
    bundle: StorageBundle,
    agent_id: str,
    steps: List[SimulationStep],
) -> str:
    registry = AgentRegistry(storage=bundle.agent_registry, supported_versions="1.x")
    st = registry.get_agent_status(agent_id)
    status_s = _esc(st[0]) if st else "—"
    susp_s = _esc(st[1] or "") if st else "—"
    contract = registry.get_agent_contract(agent_id) or {}
    mission_excerpt = str(contract.get("mission", ""))[:160]
    role = str(contract.get("role", ""))
    inst = contract.get("authorized_instruments")
    inst_s = _esc(json.dumps(inst) if inst is not None else "[]")

    reg_rows = (
        f"<tr><td>{_esc(agent_id)}</td><td>{status_s}</td><td>{registry.get_agent_priority(agent_id)}</td>"
        f"<td>{_esc(role)}</td><td>{inst_s}</td><td>{_esc(mission_excerpt)}</td></tr>"
    )

    ctx_store = ContextStore(storage=bundle.context)
    sess_rows: List[str] = []
    for s in steps[:120]:
        sess = ctx_store.get_session(s.dfid) or {}
        n_keys = len(sess.keys()) if isinstance(sess, dict) else 0
        last_act = str(sess.get("last_policy_action", "")) if isinstance(sess, dict) else ""
        sess_rows.append(
            f"<tr><td><code title=\"{_esc(s.dfid)}\">{_esc(s.dfid[:8])}...</code></td>"
            f"<td>{n_keys}</td><td>{_esc(last_act or '—')}</td></tr>"
        )
    if not sess_rows:
        sess_rows = ['<tr><td colspan="3" class="muted">No sessions resolved.</td></tr>']

    return f"""
<details class="panel kernel-artefacts">
  <summary><strong>§17.4 — DIR kernel artefacts</strong> (registry, lifecycle, context)</summary>
  <h3>Agent registry snapshot</h3>
  <p class="muted">Suspension reason: {susp_s}</p>
  <table>
    <thead><tr><th>Agent</th><th>Status</th><th>Priority</th><th>Role</th><th>Instruments</th><th>Mission (excerpt)</th></tr></thead>
    <tbody>{reg_rows}</tbody>
  </table>
  <h3>Flow lifecycle transitions</h3>
  <p class="muted">No <code>bundle.lifecycle.record_transition</code> calls in this sample — aggregate suspension is via
    <code>AgentRegistry.set_agent_status</code> (see audit <code>AGENT_SUSPENDED</code>).</p>
  <h3>Context store sessions</h3>
  <table>
    <thead><tr><th>DFID</th><th>Session keys</th><th>last_policy_action</th></tr></thead>
    <tbody>{"".join(sess_rows)}</tbody>
  </table>
</details>
"""


def _format_y_tick(v: float) -> str:
    if abs(v - round(v)) < 0.05:
        return str(int(round(v)))
    return f"{v:.1f}"


def _x_tick_indices(n: int) -> List[int]:
    """1-based labels; indices 0..n-1 on plot."""
    if n <= 0:
        return []
    if n == 1:
        return [0]
    if n <= 12:
        return sorted({0, n - 1, *range(0, n, max(1, n // 3))})
    return sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})


def _svg_unified_monitor_chart(
    discounts: List[float],
    moving_avg: List[Optional[float]],
    *,
    window: int,
    monitor_threshold: float,
    dim_cap: float,
    suspension_idx: Optional[int],
    width: int = 900,
    height: int = 460,
) -> str:
    """
    Single chart: per-offer line, rolling average, monitor + DIM horizontals, suspension marker.
    Rolling average is drawn under the per-offer line so spikes remain visible.
    """
    if not discounts:
        return '<p class="muted">No executed discounts to plot.</p>'
    n = len(discounts)
    if len(moving_avg) != n:
        moving_avg = [*moving_avg, *([None] * max(0, n - len(moving_avg)))][:n]
    ma_vals = [x for x in moving_avg if x is not None]
    vmin = 0.0
    vmax = max(
        float(dim_cap),
        max(discounts),
        max(ma_vals) if ma_vals else 0.0,
        float(monitor_threshold),
    ) + 1.5
    pad_l, pad_r, pad_t, pad_b = 56.0, 28.0, 40.0, 92.0
    left = pad_l
    right = float(width - pad_r)
    top = pad_t
    bottom = float(height - pad_b)
    wplot = right - left
    hplot = bottom - top

    def x_for(i: int) -> float:
        return left + (i / max(n - 1, 1)) * wplot

    def y_for(v: float) -> float:
        return top + (1.0 - (v - vmin) / (vmax - vmin)) * hplot

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" class="chart" '
        f'role="img" aria-label="Per-offer discount, rolling average, thresholds, suspension">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="var(--bg)" rx="6"/>',
        f'<text x="{width / 2:.0f}" y="26" text-anchor="middle" fill="var(--fg)" '
        f'font-size="15" font-weight="600">'
        f"Per-offer vs {window}-offer rolling average, monitor and DIM (%)</text>",
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" '
        'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" '
        'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
    ]

    for val, stroke, dash, label, label_x, anchor in (
        (
            monitor_threshold,
            "#d29922",
            "5 4",
            f"Monitor {monitor_threshold:.1f}%",
            left + 6,
            "start",
        ),
        (
            dim_cap,
            "#6e7681",
            "8 5",
            f"DIM cap {dim_cap:.0f}%",
            right - 6,
            "end",
        ),
    ):
        if vmin <= val <= vmax:
            y = y_for(val)
            parts.append(
                f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                f'stroke="{stroke}" stroke-width="1.35" stroke-dasharray="{dash}" opacity="0.92"/>'
                f'<text x="{label_x:.1f}" y="{y - 7:.1f}" text-anchor="{anchor}" fill="{stroke}" '
                f'font-size="11" font-weight="500">{label}</text>'
            )

    for yv in (vmin, (vmin + vmax) / 2, vmax):
        yy = y_for(yv)
        parts.append(
            f'<line x1="{left - 5}" y1="{yy:.1f}" x2="{left}" y2="{yy:.1f}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.4"/>'
            f'<text x="{left - 8}" y="{yy + 4:.1f}" text-anchor="end" fill="var(--muted)" '
            f'font-size="11">{_format_y_tick(yv)}</text>'
        )

    ma_pts: List[str] = []
    for i, m in enumerate(moving_avg):
        if m is not None:
            ma_pts.append(f"{x_for(i):.1f},{y_for(m):.1f}")
    if len(ma_pts) >= 2:
        parts.append(
            f'<polyline fill="none" stroke="#a371f7" stroke-width="2.4" stroke-dasharray="7 4" '
            f'opacity="0.95" points="{" ".join(ma_pts)}"/>'
        )
    elif len(ma_pts) == 1:
        cx, cy = ma_pts[0].split(",")
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="#a371f7"/>')

    pts_offer = " ".join(f"{x_for(i):.1f},{y_for(d):.1f}" for i, d in enumerate(discounts))
    parts.append(
        f'<polyline fill="none" stroke="#58a6ff" stroke-width="2.6" points="{pts_offer}"/>'
    )

    for ti in _x_tick_indices(n):
        xx = x_for(ti)
        lab = str(ti + 1)
        parts.append(
            f'<line x1="{xx:.1f}" y1="{bottom}" x2="{xx:.1f}" y2="{bottom + 6}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.6"/>'
            f'<text x="{xx:.1f}" y="{bottom + 22}" text-anchor="middle" fill="var(--muted)" '
            f'font-size="11">{lab}</text>'
        )

    parts.append(
        f'<text x="{(left + right) / 2:.0f}" y="{height - 20}" text-anchor="middle" '
        f'fill="var(--fg)" font-size="12" font-weight="500">'
        f"Executed retention decision # (chronological)</text>"
    )

    if suspension_idx is not None and 0 <= suspension_idx < n:
        sx = x_for(suspension_idx)
        susp_ma = moving_avg[suspension_idx]
        parts.append(
            f'<line x1="{sx:.1f}" y1="{top}" x2="{sx:.1f}" y2="{bottom}" '
            'stroke="#f85149" stroke-width="2.2" stroke-dasharray="6 4" opacity="0.95"/>'
        )
        label_x = min(sx + 10.0, right - 4.0)
        anchor = "start" if label_x > sx + 4 else "middle"
        parts.append(
            f'<text x="{label_x:.1f}" y="{top + 18:.1f}" text-anchor="{anchor}" fill="#f85149" '
            'font-size="11" font-weight="700">Suspended</text>'
        )
        if susp_ma is not None:
            sy = y_for(susp_ma)
            parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="7" fill="#f85149" stroke="var(--bg)" '
                'stroke-width="2"/>'
                f'<text x="{min(sx + 12.0, right - 4.0):.1f}" y="{max(sy - 8.0, top + 8.0):.1f}" '
                f'text-anchor="start" fill="#f85149" font-size="10" font-weight="600">'
                f"Avg {susp_ma:.2f}% &gt; {monitor_threshold:.1f}%</text>"
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _legend_unified_block(
    monitor_threshold: float,
    dim_cap: float,
    window: int,
) -> str:
    return f"""
    <ul class="chart-legend" aria-label="Chart legend">
      <li><span class="swatch line-solid"></span> Per-offer discount (≤ DIM {dim_cap:.1f}%)</li>
      <li><span class="swatch line-purple"></span> Rolling average (last {window} executed offers)</li>
      <li><span class="swatch line-warn"></span> Monitor threshold ({monitor_threshold:.1f}%)</li>
      <li><span class="swatch line-cap"></span> DIM hard cap ({dim_cap:.1f}%)</li>
      <li><span class="swatch line-suspend"></span> Suspension: vertical line at last executed decision</li>
      <li><span class="swatch dot-suspend"></span> Dot on purple: rolling avg when monitor tripped</li>
    </ul>
    """


def generate_report(
    sample_dir: Path,
    bundle: StorageBundle,
    *,
    simulation_id: str,
    window: int,
    agent_id: str,
    max_discount_pct: float,
    threshold_pct: float,
    llm_backend: str = "Mock",
    slug: str = "",
) -> Path:
    """Build HTML exclusively from ``decision_audit.all_events_chronological()`` (§17.3)."""
    events = bundle.decision_audit.all_events_chronological()
    sim = hydrate_simulation_result(events, simulation_id)
    slug_use = slug or "".join(
        c if c.isalnum() or c in "-_" else "_" for c in simulation_id
    ).strip("_")[:48] or "retention_drift"
    out = _new_report_path(sample_dir, slug=slug_use)

    counts = _count_events_for_simulation(events, simulation_id)
    n_run = sum(counts.values())
    elapsed = _run_elapsed_seconds(events, simulation_id)
    n_audit = len(events)
    discounts_exec = [s.discount_offered for s in sim.steps if s.executed]
    n_exec = len(discounts_exec)
    ma_series = moving_average_series(discounts_exec, window)

    suspended = sim.stopped_reason == "profitability_drift_monitor"
    suspend_idx = len(discounts_exec) - 1 if suspended and discounts_exec else None

    ma_aligned: List[Optional[float]] = []
    if len(ma_series) >= len(discounts_exec):
        ma_aligned = list(ma_series[: len(discounts_exec)])
    else:
        ma_aligned = [*ma_series, *([None] * (len(discounts_exec) - len(ma_series)))]

    chart_main = (
        '<figure class="chart-wrap" aria-label="Discount trajectory and rolling monitor average">'
        + _svg_unified_monitor_chart(
            discounts_exec,
            ma_aligned,
            window=window,
            monitor_threshold=threshold_pct,
            dim_cap=max_discount_pct,
            suspension_idx=suspend_idx,
        )
        + _legend_unified_block(threshold_pct, max_discount_pct, window)
        + "</figure>"
    )

    registry = AgentRegistry(storage=bundle.agent_registry, supported_versions="1.x")
    registry_status = registry.get_agent_status(agent_id)
    status_s = "—"
    reason_s = "—"
    if registry_status:
        status_s = _esc(registry_status[0])
        reason_s = _esc(registry_status[1] or "")

    rows_html: List[str] = []
    for s in sim.steps:
        ma = s.moving_avg_after
        ma_s = f"{ma:.2f}" if ma is not None else "—"
        reason_cell = (
            f'<td class="reason" title="{_esc(s.user_reason)}">{_esc(s.user_reason)}</td>'
        )
        badge = "accept" if s.dim_verdict == "ACCEPT" else (
            "reject" if s.dim_verdict == "REJECT" else "muted"
        )
        detail_inner = (
            f"<p><strong>Explain</strong></p><pre class=\"reason\">{_esc(s.explain_narrative)}</pre>"
            f"<p><strong>Policy justification</strong></p><pre class=\"reason\">{_esc(s.justification)}</pre>"
            f"<p><strong>DIM reason</strong></p><pre class=\"reason\">{_esc(s.dim_reason)}</pre>"
        )
        rows_html.append(
            "<tr>"
            f"<td>{s.iteration + 1}</td>"
            f'<td><code title="{_esc(s.dfid)}">{_esc(s.dfid[:8])}...</code></td>'
            f"<td>{_esc(s.input_ref)}</td>"
            f"<td>{_esc(s.plan)}</td>"
            f"<td>{_esc(s.channel)}</td>"
            f"{reason_cell}"
            f"<td>{s.discount_offered:.2f}</td>"
            f'<td><span class="badge {badge}">{_esc(s.dim_verdict)}</span></td>'
            f"<td>{'yes' if s.executed else 'no'}</td>"
            f"<td>{ma_s}</td>"
            f"<td>{_esc(s.console_note or '')}</td>"
            f"<td><details><summary>Reasoning</summary>{detail_inner}</details></td>"
            "</tr>"
        )

    if sim.suspension_decision_number is not None:
        susp_block = (
            f'<div class="panel susp">'
            f"<h2>Agent suspension</h2>"
            f"<p>After retention decision <strong>#{sim.suspension_decision_number}</strong>, "
            f"the PerformanceMonitor detected rolling average discount above "
            f"<strong>{threshold_pct:.1f}%</strong>. "
            f"The registry moved <code>{_esc(agent_id)}</code> to "
            f"<strong>SUSPENDED</strong> (reason: {reason_s}).</p>"
            f"</div>"
        )
    else:
        susp_block = (
            '<div class="panel"><h2>Agent suspension</h2>'
            "<p class=\"muted\">No suspension in this run (all inputs processed or other stop).</p>"
            "</div>"
        )

    sec1_metrics = f"""
  <div class="panel summary">
    <h2>Run summary</h2>
    <p class="muted">Sample 36 — classic topology — generated {_esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}</p>
    <div class="metric-grid">
      <div><span class="lbl">simulation_id</span><br/><code>{_esc(simulation_id)}</code></div>
      <div><span class="lbl">inputs processed (steps)</span><br/>{len(sim.steps)} / {sim.total_inputs}</div>
      <div><span class="lbl">executed discounts</span><br/>{n_exec}</div>
      <div><span class="lbl">telemetry rows (run)</span><br/>{n_run}</div>
      <div><span class="lbl">telemetry rows (DB total)</span><br/>{n_audit}</div>
      <div><span class="lbl">elapsed (start→end)</span><br/>{_esc(f"{elapsed:.2f}s" if elapsed is not None else "—")}</div>
      <div><span class="lbl">AGENT_DECISION</span><br/>{counts.get("AGENT_DECISION", 0)}</div>
      <div><span class="lbl">RETENTION_EXECUTED</span><br/>{counts.get("RETENTION_EXECUTED", 0)}</div>
      <div><span class="lbl">MONITOR_TICK</span><br/>{counts.get("MONITOR_TICK", 0)}</div>
    </div>
    <p><strong>Agent</strong> {_esc(agent_id)} &mdash; <strong>Registry</strong> {status_s}
       &mdash; <strong>Suspension</strong> {reason_s} &mdash; <strong>LLM</strong> {_esc(llm_backend)}</p>
    <p><strong>DIM cap</strong> {max_discount_pct:.1f}% &mdash; <strong>Monitor</strong> last {window} avg &gt; {threshold_pct:.1f}%</p>
  </div>
"""

    experiment_block = f"""
  <div class="panel experiment">
    <h2>What this run demonstrates</h2>
    <p>This sample illustrates <strong>optimization drift (reward hacking)</strong> in a
       subscription-retention workflow. The agent's primary objective is to retain subscribers
       by offering a discount. To maximize retention it increases the discount over time, staying
       under the <strong>DIM hard cap of {max_discount_pct:.0f}%</strong> per offer.</p>
    <p>The <strong>Decision Integrity Module (DIM)</strong> enforces only what is encoded in the
       kernel contract (here: <code>discount_offered ≤ {max_discount_pct:.0f}%</code>, schema,
       RBAC, TTL). It does <em>not</em> evaluate margin trajectory or running average concession.
       Therefore the agent can remain "kernel-compliant" while the average discount drifts far
       above what is economically sustainable — a pattern sometimes called
       <em>death by a thousand cuts</em>.</p>
    <p><strong>Simulation design:</strong> The first <strong>{window}</strong> offers (phase A)
       fluctuate around ~{threshold_pct * 0.55:.1f}% with small random spread — a healthy margin
       band. From decision {window + 1} onward (phase B), a slow accelerating curve plus two
       independent noise bands drive offers upward. Individual offers may spike <em>above</em>
       the rolling average for many steps without triggering the monitor.</p>
    <p><strong>PerformanceMonitor:</strong> After each accepted execution, the sample recomputes
       the rolling average of <code>discount_offered</code> over the last <strong>{window}</strong>
       <code>RETENTION_EXECUTED</code> rows in canonical <code>decision_audit_events</code>,
       filtered by <code>simulation_id</code> (correlation integrity). If that average exceeds
       <strong>{threshold_pct:.1f}%</strong>, the agent is moved to <code>SUSPENDED</code> with
       reason <code>PROFITABILITY_DRIFT</code>.</p>
    <p><strong>How to read the chart:</strong> The blue line is each individual offer (hard-capped
       by DIM). The purple dashed line is the rolling mean — it rises more slowly than single
       offers because it averages over the last {window} decisions. Suspension fires when
       <em>purple crosses orange</em>, not when a single blue spike appears above it. The red
       vertical line and dot mark the exact decision where the monitor tripped.</p>
  </div>
"""

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Sample 36 — Retention optimization drift</title>
  <style>
    :root {{
      --bg: #0f1419;
      --fg: #e6edf3;
      --muted: #8b949e;
      --border: #30363d;
      --ok: #3fb950;
      --reject: #f85149;
      --warn: #d29922;
      --info: #58a6ff;
      --line: #58a6ff;
      --line2: #a371f7;
      --cap: #6e7681;
      --suspend: #f85149;
    }}
    body {{
      font-family: system-ui, sans-serif;
      background: #010409;
      color: var(--fg);
      margin: 0;
      padding: 2rem;
      line-height: 1.5;
    }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; }}
    h2 {{ font-size: 1.05rem; margin-top: 1.5rem; }}
    .muted {{ color: var(--muted); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
      margin-top: 1rem;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.45rem 0.55rem;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #161b22; }}
    td.reason {{
      max-width: 22rem;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 0.84rem;
    }}
    .chart-wrap {{
      margin: 1rem 0 1.5rem;
      padding: 0.75rem 0 0;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #0d1117;
      overflow: hidden;
    }}
    .chart-wrap .chart {{
      display: block;
      width: 100%;
      height: auto;
      border-radius: 0;
    }}
    .chart-legend {{
      list-style: none;
      margin: 0;
      padding: 0.65rem 1rem 1rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem 1.5rem;
      font-size: 0.82rem;
      color: var(--muted);
      border-top: 1px solid var(--border);
      background: #161b22;
    }}
    .chart-legend li {{ display: flex; align-items: center; gap: 0.45rem; margin: 0; }}
    .swatch {{
      display: inline-block;
      width: 1.35rem;
      height: 0;
      border-bottom: 3px solid;
      flex-shrink: 0;
    }}
    .swatch.line-solid {{ border-color: #58a6ff; width: 1.6rem; }}
    .swatch.line-warn {{ border-color: #d29922; border-style: dashed; width: 1.6rem; }}
    .swatch.line-cap {{ border-color: #6e7681; border-style: dashed; width: 1.6rem; }}
    .swatch.line-suspend {{ border-color: #f85149; border-style: dashed; width: 1.6rem; }}
    .swatch.line-purple {{ border-color: #a371f7; width: 1.6rem; }}
    .swatch.dot-suspend {{
      width: 0.55rem;
      height: 0.55rem;
      border: none;
      border-radius: 50%;
      background: #f85149;
      border-bottom: none;
    }}
    .panel {{
      background: #161b22;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem 1.25rem;
      margin: 1rem 0;
    }}
    .panel.susp {{ border-color: var(--suspend); }}
    .panel.experiment h2 {{ margin-top: 0; }}
    .panel.experiment p {{ margin: 0.65rem 0 0 0; }}
    .panel.experiment p:first-of-type {{ margin-top: 0; }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
      gap: 0.65rem 1rem;
      margin: 0.75rem 0 1rem;
      font-size: 0.88rem;
    }}
    .metric-grid .lbl {{ color: var(--muted); font-size: 0.78rem; }}
    .badge {{
      display: inline-block;
      padding: 0.1rem 0.45rem;
      border-radius: 4px;
      font-size: 0.8rem;
      font-weight: 600;
    }}
    .badge.accept {{ background: rgba(63, 185, 80, 0.15); color: var(--ok); }}
    .badge.reject {{ background: rgba(248, 81, 73, 0.15); color: var(--reject); }}
    .badge.muted {{ background: #21262d; color: var(--muted); }}
    .roa-block pre.reason {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
<main>
  <h1>Sample 36 — Optimization drift (retention discounts) — classic</h1>
  <p class="muted">Stopped: <strong>{_esc(sim.stopped_reason)}</strong></p>

  {sec1_metrics}

  {experiment_block}

  {susp_block}

  <h2>Charts — discount trajectory and monitor</h2>
  <p class="muted">One timeline over executed decisions: blue = each offer (DIM-capped), purple dashed =
     rolling average of the last {window} offers, orange/grey = monitor and DIM ceilings. A single blue spike
     above purple is allowed until the <strong>purple</strong> line crosses orange; red vertical line + dot
     mark the trip and agent suspension.</p>
  {chart_main}

  <h2>Per-decision trace</h2>
  <p class="muted">Text in <strong>Subscriber reason</strong> comes from the export
     <code>data/cancelation.json</code>. Expand <strong>Reasoning</strong> for Explain, Policy, and DIM.</p>
  <table>
    <thead>
      <tr>
        <th>#</th><th>DFID</th><th>Ticket</th><th>Plan</th><th>Channel</th>
        <th>Subscriber reason</th><th>Discount %</th>
        <th>DIM</th><th>Executed</th><th>Mov. avg</th><th>Note</th><th>Details</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>

  {_section5_roa_audit_blocks(sim, agent_id)}

  <div class="panel">
    <h2>Entity lifecycle</h2>
    <p class="muted">No long-lived domain entities in this sample — each row is one cancellation ticket and one
       <code>dfid</code>. Persistent registry state is the agent row only.</p>
  </div>

  {_section7_kernel_html(bundle, agent_id, sim.steps)}
</main>
</body>
</html>
"""
    out.write_text(doc, encoding="utf-8")
    return out


def build_report_payload_for_tests(
    bundle: StorageBundle,
    simulation_id: str,
    window: int,
) -> Dict[str, Any]:
    """Lightweight structure for optional pytest consumers."""
    from performance_monitor import executed_discounts_for_simulation

    disc = executed_discounts_for_simulation(bundle, simulation_id)
    series = moving_average_series(disc, window)
    return {
        "execution_count": len(disc),
        "moving_average_tail": series[-5:] if series else [],
    }


def _latest_simulation_id(bundle: StorageBundle) -> Optional[str]:
    for row in reversed(bundle.decision_audit.all_events_chronological()):
        if row.get("event") != "SIMULATION_START":
            continue
        details = row.get("details") or {}
        sid = details.get("simulation_id")
        if isinstance(sid, str) and sid:
            return sid
    return None


def hydrate_simulation_result(
    events: List[Dict[str, Any]],
    simulation_id: str,
) -> SimulationResult:
    """Rebuild :class:`SimulationResult` from ``decision_audit`` rows (offline report)."""
    filtered = [
        e
        for e in events
        if (e.get("details") or {}).get("simulation_id") == simulation_id
        and e.get("event") not in ("SIMULATION_START", "SIMULATION_END")
    ]
    by_dfid: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for e in filtered:
        dfid = str(e.get("dfid") or "")
        if not dfid:
            continue
        if dfid not in by_dfid:
            by_dfid[dfid] = {}
            order.append(dfid)
        acc = by_dfid[dfid]
        d = e.get("details") or {}
        et = e.get("event") or ""
        if et == "CONTEXT_COMPILED":
            acc["input_ref"] = str(d.get("input_ref", ""))
            acc["plan"] = str(d.get("plan", ""))
            acc["channel"] = str(d.get("channel", ""))
            acc["user_reason"] = str(d.get("user_reason", ""))
        elif et == "POLICY_PROPOSAL":
            acc["discount_offered"] = float(d.get("discount_offered", 0.0))
        elif et == "DIM_VALIDATION":
            acc["dim_verdict"] = str(e.get("state") or "")
            acc["dim_reason"] = str(d.get("reason", ""))
        elif et == "RETENTION_EXECUTED":
            acc["executed"] = True
            acc["discount_offered"] = float(
                d.get("discount_offered", acc.get("discount_offered", 0.0))
            )
        elif et == "AGENT_DECISION":
            acc.setdefault("dim_verdict", str(d.get("verdict", "")))
            acc["explain_narrative"] = str(d.get("explain_narrative", ""))
            acc["justification"] = str(d.get("justification", ""))
        elif et == "MONITOR_TICK" and d.get("moving_avg_discount_pct") is not None:
            acc["moving_avg_after"] = float(d["moving_avg_discount_pct"])

    steps: List[SimulationStep] = []
    for i, dfid in enumerate(order):
        a = by_dfid[dfid]
        steps.append(
            SimulationStep(
                iteration=i,
                dfid=dfid,
                input_ref=str(a.get("input_ref", "")),
                plan=str(a.get("plan", "")),
                user_reason=str(a.get("user_reason", "")),
                channel=str(a.get("channel", "")),
                discount_offered=float(a.get("discount_offered", 0.0)),
                dim_verdict=str(a.get("dim_verdict", "")),
                dim_reason=str(a.get("dim_reason", "")),
                executed=bool(a.get("executed")),
                moving_avg_after=a.get("moving_avg_after"),
                console_note="",
                explain_narrative=str(a.get("explain_narrative", "")),
                justification=str(a.get("justification", "")),
            )
        )

    total_inputs = len(steps)
    for e in events:
        if e.get("event") != "SIMULATION_START":
            continue
        d = e.get("details") or {}
        if d.get("simulation_id") != simulation_id:
            continue
        ti = d.get("total_inputs")
        if isinstance(ti, int):
            total_inputs = ti
        break

    stopped = "replay"
    for e in reversed(events):
        if e.get("event") != "SIMULATION_END":
            continue
        d = e.get("details") or {}
        if d.get("simulation_id") != simulation_id:
            continue
        stopped = str(d.get("stopped_reason") or d.get("status") or "replay")
        break

    suspension_decision_number: Optional[int] = None
    for e in filtered:
        if e.get("event") != "AGENT_SUSPENDED":
            continue
        susp_dfid = str(e.get("dfid") or "")
        if susp_dfid in order:
            suspension_decision_number = order.index(susp_dfid) + 1
        stopped = "profitability_drift_monitor"
        break

    return SimulationResult(
        steps=steps,
        stopped_reason=stopped,
        total_inputs=total_inputs,
        suspension_decision_number=suspension_decision_number,
    )


if __name__ == "__main__":
    from shared.bootstrap import setup_environment

    from mocks import make_mock_strategy
    from schemas import (  # type: ignore[attr-defined]
        load_retention_full_config,
        load_retention_sample_config_bundle,
    )

    ap = argparse.ArgumentParser(description="Regenerate HTML report from canonical audit.")
    ap.add_argument(
        "--simulation-id",
        default=None,
        help="Telemetry simulation_id (default: latest SIMULATION_START in DB)",
    )
    ap.add_argument("--output-path", default=None, type=Path, help="Optional output HTML path")
    args = ap.parse_args()

    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    config = load_retention_full_config(sample_dir)
    cfg = load_retention_sample_config_bundle(sample_dir)

    env = setup_environment(
        config,
        mock_llm_strategy=make_mock_strategy(),
        config_path=str(config_path),
    )
    bundle = env.repository
    resolved = args.simulation_id or _latest_simulation_id(bundle) or cfg.simulation.run_id

    events = bundle.decision_audit.all_events_chronological()
    if not any(
        (e.get("details") or {}).get("simulation_id") == resolved
        for e in events
        if e.get("event") == "CONTEXT_COMPILED"
    ):
        print(
            f"No audit rows for simulation_id={resolved}; run run.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    agent_id = cfg.agent.agent_id
    out = generate_report(
        sample_dir,
        bundle,
        simulation_id=resolved,
        window=cfg.monitor.window_size,
        agent_id=agent_id,
        max_discount_pct=cfg.contract.max_discount_pct,
        threshold_pct=cfg.monitor.avg_threshold_pct,
        llm_backend="offline",
    )
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(args.output_path)
    else:
        print(out)
