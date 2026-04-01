"""
HTML report: discount drift, rolling average, suspension, decision history, user reasons.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from audit_store import AuditStore

from pipeline import SimulationResult, moving_average_series


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _new_report_path(sample_dir: Path) -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return results_dir / f"simulation_report_{stamp}.html"


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
    audit: AuditStore,
    sim: SimulationResult,
    *,
    window: int,
    agent_id: str,
    registry_status: Optional[tuple],
    max_discount_pct: float,
    threshold_pct: float,
) -> Path:
    out = _new_report_path(sample_dir)
    ma_series = moving_average_series(audit, window)

    discounts_exec = [s.discount_offered for s in sim.steps if s.executed]
    suspended = sim.stopped_reason == "profitability_drift_monitor"
    suspend_idx = len(discounts_exec) - 1 if suspended and discounts_exec else None

    ma_aligned: List[Optional[float]] = []
    if len(ma_series) >= len(discounts_exec):
        ma_aligned = list(ma_series[: len(discounts_exec)])
    else:
        ma_aligned = [*ma_series, *([None] * (len(discounts_exec) - len(ma_series)))]

    chart_main = (
        '<figure class="chart-wrap">'
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

    rows_html = []
    for s in sim.steps:
        ma = s.moving_avg_after
        ma_s = f"{ma:.2f}" if ma is not None else "—"
        reason_cell = (
            f'<td class="reason" title="{_esc(s.user_reason)}">{_esc(s.user_reason)}</td>'
        )
        rows_html.append(
            "<tr>"
            f"<td>{s.iteration + 1}</td>"
            f"<td><code>{_esc(s.dfid[:8])}...</code></td>"
            f"<td>{_esc(s.input_ref)}</td>"
            f"<td>{_esc(s.plan)}</td>"
            f"<td>{_esc(s.channel)}</td>"
            f"{reason_cell}"
            f"<td>{s.discount_offered:.2f}</td>"
            f"<td>{_esc(s.dim_verdict)}</td>"
            f"<td>{'yes' if s.executed else 'no'}</td>"
            f"<td>{ma_s}</td>"
            f"<td>{_esc(s.console_note or '')}</td>"
            "</tr>"
        )

    status_s = "—"
    reason_s = "—"
    if registry_status:
        status_s = _esc(registry_status[0])
        reason_s = _esc(registry_status[1] or "")

    if sim.suspension_decision_number is not None:
        susp_block = (
            f'<div class="panel susp">'
            f"<h2>Agent suspension</h2>"
            f"<p>After retention decision <strong>#{sim.suspension_decision_number}</strong>, "
            f"the PerformanceMonitor detected rolling average discount above "
            f"<strong>{threshold_pct:.1f}%</strong>. "
            f"The registry moved <code>{_esc(agent_id)}</code> to "
            f"<strong>SUSPENDED</strong> (reason: {_esc(reason_s)}).</p>"
            f"</div>"
        )
    else:
        susp_block = (
            '<div class="panel"><h2>Agent suspension</h2>'
            "<p class=\"muted\">No suspension in this run (all inputs processed or other stop).</p>"
            "</div>"
        )

    experiment_block = f"""
  <div class="panel experiment">
    <h2>What this experiment demonstrates</h2>
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
    <p><strong>PerformanceMonitor:</strong> After each accepted execution, a SQL query computes
       the rolling average of <code>discount_offered</code> over the last <strong>{window}</strong>
       rows of <code>execution_log</code>, joined to <code>decision_flows</code> on
       <code>dfid</code> (correlation integrity). If that average exceeds
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
  <title>Sample 36 - Retention optimization drift</title>
  <style>
    :root {{
      --bg: #0f1419;
      --fg: #e6edf3;
      --muted: #8b949e;
      --line: #58a6ff;
      --line2: #a371f7;
      --border: #30363d;
      --warn: #d29922;
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
  </style>
</head>
<body>
<main>
  <h1>Sample 36 — Optimization drift (retention discounts)</h1>
  <p class="muted">Simulation stopped: <strong>{_esc(sim.stopped_reason)}</strong>.
     Decisions recorded: {len(sim.steps)} / {sim.total_inputs} input tickets.</p>

  {experiment_block}

  <div class="panel">
    <p><strong>Agent</strong> {_esc(agent_id)}</p>
    <p><strong>Registry status</strong> {status_s}
       &nbsp;|&nbsp; <strong>Suspension reason</strong> {reason_s}</p>
    <p><strong>Hard limit (DIM)</strong> max_discount_pct =
       {max_discount_pct:.1f}%
       &nbsp;|&nbsp; <strong>Monitor threshold</strong> rolling {window}
       avg &gt; {threshold_pct:.1f}%</p>
  </div>

  {susp_block}

  <h2>Discount trajectory and monitor</h2>
  <p class="muted">One timeline over executed decisions: blue = each offer (DIM-capped), purple dashed =
     rolling average of the last {window} offers, orange/grey = monitor and DIM ceilings. A single blue spike
     above purple is allowed until the <strong>purple</strong> line crosses orange; red vertical line + dot
     mark the trip and agent suspension.</p>
  {chart_main}

  <h2>Decision history and subscriber cancellation reasons</h2>
  <p class="muted">Text in <strong>Subscriber reason</strong> comes from the export
     <code>data/cancelation.json</code> (user-supplied messages as in a real support dump).</p>
  <table>
    <thead>
      <tr>
        <th>#</th><th>DFID</th><th>Ticket</th><th>Plan</th><th>Channel</th>
        <th>Subscriber reason</th><th>Discount %</th>
        <th>DIM</th><th>Executed</th><th>Mov. avg</th><th>Note</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</main>
</body>
</html>
"""
    out.write_text(doc, encoding="utf-8")
    return out


def build_report_payload_for_tests(
    audit: AuditStore,
    window: int,
) -> Dict[str, Any]:
    """Lightweight structure for optional pytest consumers."""
    return {
        "execution_count": audit.execution_count(),
        "moving_average_tail": moving_average_series(audit, window)[-5:],
    }
