"""
HTML report: CPC bids, rolling avg vs LTV, environmental drift suspension, cycle trace.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from audit_store import AuditStore

from models import BiddingSampleConfig
from pipeline import SimulationResult, rolling_avg_cpc_series


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _new_report_path(sample_dir: Path) -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return results_dir / f"simulation_report_{stamp}.html"


def _x_tick_indices(n: int) -> List[int]:
    if n <= 0:
        return []
    if n == 1:
        return [0]
    if n <= 12:
        return sorted({0, n - 1, *range(0, n, max(1, n // 3))})
    return sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})


def _svg_cpc_roi_charts(
    bids: List[float],
    rolling_avg: List[Optional[float]],
    *,
    window: int,
    max_cpc_usd: float,
    ltv_usd: float,
    suspension_idx: Optional[int],
    width: int = 900,
    height: int = 560,
) -> str:
    if not bids or len(bids) != len(rolling_avg):
        return '<p class="muted">No executed bids to plot.</p>'
    n = len(bids)
    pad_l, pad_r = 58.0, 24.0
    left = pad_l
    right = float(width - pad_r)
    wplot = right - left

    y_top0, y_top1 = 52.0, 230.0
    y_bot0, y_bot1 = 258.0, 448.0
    axis_bottom = 492.0

    h_top = y_top1 - y_top0
    h_bot = y_bot1 - y_bot0

    def x_for(i: int) -> float:
        return left + (i / max(n - 1, 1)) * wplot

    vmin_usd = min(1.0, ltv_usd * 0.85, min(bids) * 0.95)
    vmax_usd = max(max_cpc_usd, ltv_usd, max(bids)) * 1.08
    for v in rolling_avg:
        if v is not None:
            vmax_usd = max(vmax_usd, v * 1.05)

    def y_usd(u: float, y0: float, y1: float, h: float) -> float:
        return y1 - (u - vmin_usd) / (vmax_usd - vmin_usd) * h

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'class="chart" role="img" aria-label="CPC bids and rolling average vs LTV">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="var(--bg)" rx="6"/>',
        f'<text x="{width / 2:.0f}" y="22" text-anchor="middle" fill="var(--fg)" '
        f'font-size="15" font-weight="600">Figure 1 — CPC bids and ROI monitor (rolling avg CPC)</text>',
        f'<text x="{width / 2:.0f}" y="40" text-anchor="middle" fill="var(--muted)" '
        f'font-size="11">Horizontal axis: execution index (chronological accepted bids)</text>',
        f'<text x="{left:.0f}" y="{y_top0 - 6:.0f}" text-anchor="start" fill="var(--fg)" '
        f'font-size="12" font-weight="600">A. CPC bid per execution</text>',
        f'<line x1="{left}" y1="{y_top1}" x2="{right}" y2="{y_top1}" '
        'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
        f'<line x1="{left}" y1="{y_top0}" x2="{left}" y2="{y_top1}" '
        'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
    ]

    y_cap = y_usd(max_cpc_usd, y_top0, y_top1, h_top)
    if y_top0 <= y_cap <= y_top1:
        parts.append(
            f'<line x1="{left}" y1="{y_cap:.1f}" x2="{right}" y2="{y_cap:.1f}" '
            'stroke="#6e7681" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.9"/>'
            f'<text x="{right - 4:.1f}" y="{max(y_cap - 6, y_top0 + 10):.1f}" text-anchor="end" '
            f'fill="#6e7681" font-size="10">DIM max {max_cpc_usd:.2f} USD</text>'
        )
    y_ltv_top = y_usd(ltv_usd, y_top0, y_top1, h_top)
    if y_top0 <= y_ltv_top <= y_top1:
        parts.append(
            f'<line x1="{left}" y1="{y_ltv_top:.1f}" x2="{right}" y2="{y_ltv_top:.1f}" '
            'stroke="#d29922" stroke-width="1.35" stroke-dasharray="5 4" opacity="0.92"/>'
            f'<text x="{left + 4:.1f}" y="{max(y_ltv_top - 4, y_top0 + 12):.1f}" text-anchor="start" '
            f'fill="#d29922" font-size="10">LTV {ltv_usd:.2f} USD</text>'
        )

    for yv, lab in (
        (vmin_usd, f"{vmin_usd:.2f}"),
        ((vmin_usd + vmax_usd) / 2, f"{(vmin_usd + vmax_usd) / 2:.2f}"),
        (vmax_usd, f"{vmax_usd:.2f}"),
    ):
        yy = y_usd(yv, y_top0, y_top1, h_top)
        parts.append(
            f'<line x1="{left - 4}" y1="{yy:.1f}" x2="{left}" y2="{yy:.1f}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.35"/>'
            f'<text x="{left - 6:.1f}" y="{yy + 4:.1f}" text-anchor="end" fill="var(--muted)" '
            f'font-size="10">{lab}</text>'
        )

    bid_pts = " ".join(f"{x_for(i):.1f},{y_usd(bids[i], y_top0, y_top1, h_top):.1f}" for i in range(n))
    parts.append(
        f'<polyline fill="none" stroke="#58a6ff" stroke-width="2.6" points="{bid_pts}"/>'
    )

    parts.extend(
        [
            f'<text x="{left:.0f}" y="{y_bot0 - 8:.0f}" text-anchor="start" fill="var(--fg)" '
            f'font-size="12" font-weight="600">B. Rolling average CPC (last {window} bids) vs LTV</text>',
            f'<text x="{left:.0f}" y="{y_bot0 + 6:.0f}" text-anchor="start" fill="var(--muted)" '
            f'font-size="10">ROI estimate = LTV − avg CPC (mean of last {window} executed bids). '
            f'Grey region: warm-up (fewer than {window} bids — rolling average undefined).</text>',
            f'<line x1="{left}" y1="{y_bot1}" x2="{right}" y2="{y_bot1}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
            f'<line x1="{left}" y1="{y_bot0}" x2="{left}" y2="{y_bot1}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
        ]
    )

    first_avg_i = next((i for i, v in enumerate(rolling_avg) if v is not None), n)
    if first_avg_i > 0:
        x_warm_end = (x_for(first_avg_i - 1) + x_for(first_avg_i)) / 2.0
        cx_w = (left + x_warm_end) / 2.0
        cy_w = (y_bot0 + y_bot1) / 2.0
        parts.append(
            f'<rect x="{left:.1f}" y="{y_bot0:.1f}" width="{x_warm_end - left:.1f}" '
            f'height="{h_bot:.1f}" fill="#30363d" opacity="0.45"/>'
            f'<text x="{cx_w:.0f}" y="{cy_w - 6:.0f}" text-anchor="middle" '
            f'fill="var(--muted)" font-size="10">Warm-up</text>'
            f'<text x="{cx_w:.0f}" y="{cy_w + 8:.0f}" text-anchor="middle" '
            f'fill="var(--muted)" font-size="10">(&lt; {window} exec)</text>'
        )

    y_ltv_bot = y_usd(ltv_usd, y_bot0, y_bot1, h_bot)
    if y_bot0 <= y_ltv_bot <= y_bot1:
        parts.append(
            f'<line x1="{left}" y1="{y_ltv_bot:.1f}" x2="{right}" y2="{y_ltv_bot:.1f}" '
            'stroke="#d29922" stroke-width="1.35" stroke-dasharray="5 4" opacity="0.92"/>'
            f'<text x="{right - 4:.1f}" y="{y_ltv_bot - 5:.1f}" text-anchor="end" fill="#d29922" '
            f'font-size="10">LTV {ltv_usd:.2f} USD</text>'
        )

    for yv, lab in (
        (vmin_usd, f"{vmin_usd:.2f}"),
        ((vmin_usd + vmax_usd) / 2, f"{(vmin_usd + vmax_usd) / 2:.2f}"),
        (vmax_usd, f"{vmax_usd:.2f}"),
    ):
        yy = y_usd(yv, y_bot0, y_bot1, h_bot)
        parts.append(
            f'<line x1="{left - 4}" y1="{yy:.1f}" x2="{left}" y2="{yy:.1f}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.35"/>'
            f'<text x="{left - 6:.1f}" y="{yy + 4:.1f}" text-anchor="end" fill="var(--muted)" '
            f'font-size="10">{lab}</text>'
        )

    ma_pts: List[str] = []
    for i, v in enumerate(rolling_avg):
        if v is not None:
            ma_pts.append(f"{x_for(i):.1f},{y_usd(v, y_bot0, y_bot1, h_bot):.1f}")
    if len(ma_pts) >= 2:
        parts.append(
            f'<polyline fill="none" stroke="#a371f7" stroke-width="2.8" '
            f'points="{" ".join(ma_pts)}"/>'
        )
    elif len(ma_pts) == 1:
        cx, cy = ma_pts[0].split(",")
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="#a371f7"/>')

    for ti in _x_tick_indices(n):
        xx = x_for(ti)
        parts.append(
            f'<line x1="{xx:.1f}" y1="{y_bot1}" x2="{xx:.1f}" y2="{y_bot1 + 5}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.55"/>'
            f'<text x="{xx:.1f}" y="{axis_bottom - 6:.1f}" text-anchor="middle" fill="var(--muted)" '
            f'font-size="11">{ti + 1}</text>'
        )

    parts.append(
        f'<text x="{(left + right) / 2:.0f}" y="{height - 14:.0f}" text-anchor="middle" '
        f'fill="var(--fg)" font-size="12" font-weight="500">Bid execution index (chronological)</text>'
    )

    if suspension_idx is not None and 0 <= suspension_idx < n:
        sx = x_for(suspension_idx)
        parts.append(
            f'<line x1="{sx:.1f}" y1="{y_top0}" x2="{sx:.1f}" y2="{y_bot1}" '
            'stroke="#f85149" stroke-width="2" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{min(sx + 8, right - 120):.1f}" y="{y_top0 + 12:.1f}" text-anchor="start" '
            f'fill="#f85149" font-size="11" font-weight="700">Suspension</text>'
        )
        susp_v = rolling_avg[suspension_idx]
        if susp_v is not None:
            sy = y_usd(susp_v, y_bot0, y_bot1, h_bot)
            parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6" fill="#f85149" stroke="var(--bg)" '
                'stroke-width="2"/>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _legend_block(window: int) -> str:
    return f"""
    <ul class="chart-legend" aria-label="Chart legend">
      <li><span class="swatch line-blue"></span> Panel A: CPC bid each execution (line)</li>
      <li><span class="swatch line-cap"></span> Panel A: DIM contract cap (max CPC)</li>
      <li><span class="swatch line-warn"></span> LTV reference (business break-even on CPC)</li>
      <li><span class="swatch zone-warm"></span> Panel B: warm-up (rolling avg not defined yet)</li>
      <li><span class="swatch line-purple"></span> Panel B: rolling average CPC (last {window} bids)</li>
      <li><span class="swatch line-suspend"></span> Red vertical line: suspension point</li>
    </ul>
    """


def generate_report(
    sample_dir: Path,
    audit: AuditStore,
    sim: SimulationResult,
    *,
    cfg: BiddingSampleConfig,
    registry_status: Optional[tuple],
) -> Path:
    out = _new_report_path(sample_dir)
    window = cfg.monitor.window_size
    ma_series = rolling_avg_cpc_series(audit, window)

    exec_steps = [s for s in sim.steps if s.executed]
    suspended = sim.stopped_reason == "roi_environmental_monitor"
    suspend_idx = len(exec_steps) - 1 if suspended and exec_steps else None

    ma_aligned: List[Optional[float]] = []
    if len(ma_series) >= len(exec_steps):
        ma_aligned = list(ma_series[: len(exec_steps)])
    else:
        ma_aligned = [*ma_series, *([None] * (len(exec_steps) - len(ma_series)))]

    bids = [float(s.bid_usd) for s in exec_steps]

    chart_main = (
        '<figure class="chart-wrap">'
        + _svg_cpc_roi_charts(
            bids,
            ma_aligned,
            window=window,
            max_cpc_usd=cfg.contract.max_cpc_usd,
            ltv_usd=cfg.monitor.ltv_usd,
            suspension_idx=suspend_idx,
        )
        + _legend_block(window)
        + "</figure>"
    )

    ltv = cfg.monitor.ltv_usd
    max_cpc = cfg.contract.max_cpc_usd
    n_need = cfg.monitor.negative_roi_consecutive_cycles
    sim_phase_a = cfg.simulation.normal_phase_iterations
    experiment_block = f"""
  <div class="panel experiment">
    <h2>What this experiment demonstrates</h2>
    <p>This sample illustrates <strong>environmental drift</strong> (Category 3 — state drift in the
       market). The agent follows its mission: maintain top placement by bidding just above the
       observed market floor. The <strong>contract hard cap</strong> is
       <strong>max_cpc_usd = {max_cpc:.2f} USD</strong>. External business reality is summarized by
       <strong>customer LTV = {ltv:.2f} USD</strong> — if realized CPC approaches or exceeds LTV,
       acquisition is unprofitable even when the agent is kernel-compliant.</p>
    <p>The <strong>Decision Integrity Module (DIM)</strong> enforces only encoded kernel rules
       (schema, RBAC, TTL, context stub, and <strong>bid ≤ {max_cpc:.2f} USD</strong>). It does
       <em>not</em> compare bids to LTV. When competitors escalate, bids can stay under the cap while
       CAC exceeds LTV — a failure mode no schema check can catch.</p>
    <p><strong>Simulation design:</strong> Roughly the first <strong>{sim_phase_a}</strong> cycles
       keep <code>market_cpc_to_win</code> in a gentler band; the remainder simulate a bidding war
       toward <strong>{cfg.simulation.market_cpc_end:.2f} USD</strong>. The simulated agent always
       bids <code>market_cpc_to_win + margin</code>, clipped to the contract ceiling.</p>
    <p><strong>BusinessROIMonitor:</strong> After each execution, SQLite joins
       <code>execution_log</code> to <code>market_snapshots</code> on <code>dfid</code> and computes
       the average CPC over the last <strong>{window}</strong> bids. Estimated ROI is
       <code>ltv_usd − avg_cpc</code>. If ROI is negative for <strong>{n_need}</strong> consecutive
       evaluated cycles, the registry moves the agent to <code>SUSPENDED</code> with reason
       <code>{_esc(cfg.monitor.suspension_reason)}</code>.</p>
    <p><strong>How to read Figure 1:</strong> Panel A shows each executed bid versus the DIM cap and
       LTV. Panel B shows the rolling average CPC; the grey warm-up band is expected until at least
       {window} bids exist. The trace table uses “—” in Avg CPC / ROI during the same warm-up.</p>
  </div>
"""

    rows_html = []
    for s in sim.steps:
        avg_s = f"{s.rolling_avg_cpc_after:.3f}" if s.rolling_avg_cpc_after is not None else "—"
        roi_s = f"{s.roi_estimate_after:.3f}" if s.roi_estimate_after is not None else "—"
        rows_html.append(
            "<tr>"
            f"<td>{s.iteration + 1}</td>"
            f"<td><code>{_esc(s.dfid[:8])}...</code></td>"
            f"<td>{_esc(s.cycle_id)}</td>"
            f"<td>{_esc(s.search_term)}</td>"
            f"<td>{s.market_cpc_to_win:.3f}</td>"
            f"<td>{s.bid_usd:.3f}</td>"
            f"<td>{_esc(s.dim_verdict)}</td>"
            f"<td>{'yes' if s.executed else 'no'}</td>"
            f"<td>{avg_s}</td>"
            f"<td>{roi_s}</td>"
            f"<td>{_esc(s.console_note or '')}</td>"
            "</tr>"
        )

    status_s = "—"
    reason_s = "—"
    if registry_status:
        status_s = _esc(registry_status[0])
        reason_s = _esc(registry_status[1] or "")

    if sim.suspension_decision_number is not None and suspended:
        susp_block = (
            f'<div class="panel susp">'
            f"<h2>Agent suspension</h2>"
            f"<p>After cycle <strong>#{sim.suspension_decision_number}</strong>, "
            f"the BusinessROIMonitor detected <strong>{n_need}</strong> consecutive cycles with "
            f"negative estimated ROI (rolling avg CPC above LTV <strong>{ltv:.2f} USD</strong>). "
            f"The registry moved <code>{_esc(cfg.agent.agent_id)}</code> to "
            f"<strong>SUSPENDED</strong> (reason: {_esc(reason_s)}).</p>"
            f"</div>"
        )
    else:
        susp_block = (
            '<div class="panel"><h2>Agent suspension</h2>'
            '<p class="muted">No suspension in this run (all inputs processed or other stop).</p>'
            "</div>"
        )

    monitor_rows = audit.list_monitor_events()
    mon_lines = []
    for ev in monitor_rows[-12:]:
        det = json.dumps(ev["details"], sort_keys=True, default=str)
        mon_lines.append(
            f"<li><code>{_esc(ev['event'])}</code> {_esc(ev['state'])} "
            f"— {_esc(det)}</li>"
        )
    mon_section = (
        '<h2>Monitor events (tail)</h2><ul class="muted">'
        + ("".join(mon_lines) if mon_lines else "<li>None</li>")
        + "</ul>"
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Sample 38 - Environmental bidding drift</title>
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
    .swatch.line-warn {{ border-color: #d29922; border-style: dashed; width: 1.6rem; }}
    .swatch.line-suspend {{ border-color: #f85149; width: 1.6rem; }}
    .swatch.line-purple {{ border-color: #a371f7; width: 1.6rem; }}
    .swatch.line-blue {{ border-color: #58a6ff; width: 1.6rem; }}
    .swatch.line-cap {{ border-color: #6e7681; border-style: dashed; width: 1.6rem; }}
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
    .swatch.zone-warm {{
      width: 1rem;
      height: 0.65rem;
      border: none;
      border-radius: 2px;
      background: #30363d;
      border-bottom: none;
    }}
  </style>
</head>
<body>
<main>
  <h1>Sample 38 — Environmental drift (ad bidding)</h1>
  <p class="muted">Run summary: simulation stopped with reason <strong>{_esc(sim.stopped_reason)}</strong>.
     Cycles processed: {len(sim.steps)} / {sim.total_inputs}.</p>

  {experiment_block}

  <div class="panel">
    <p><strong>Agent</strong> {_esc(cfg.agent.agent_id)}</p>
    <p><strong>Registry status</strong> {status_s}
       &nbsp;|&nbsp; <strong>Suspension reason</strong> {reason_s}</p>
    <p><strong>Hard limit (DIM)</strong> max_cpc_usd = {max_cpc:.2f} USD
       &nbsp;|&nbsp; <strong>Business metric (monitor)</strong> ltv_usd = {ltv:.2f} USD
       &nbsp;|&nbsp; <strong>Monitor</strong> rolling {window} bids;
       suspend after {n_need} consecutive negative ROI cycles</p>
  </div>

  {susp_block}

  <h2>Figure 1 — CPC and rolling average</h2>
  <p class="muted">Panel B warm-up until {window} executed bids; table columns Avg CPC / ROI match that behavior.</p>
  {chart_main}

  {mon_section}

  <h2>Cycle-level trace</h2>
  <p class="muted">Source: <code>data/market_conditions.json</code>. <code>market_cpc_to_win</code> is stored in
     <code>market_snapshots</code> at compile time (kernel fact), not inferred from the agent output.</p>
  <table>
    <thead>
      <tr>
        <th>#</th><th>DFID</th><th>Cycle</th><th>Search term</th><th>Market CPC</th><th>Bid USD</th>
        <th>DIM</th><th>Executed</th><th>Avg CPC</th><th>ROI est.</th><th>Note</th>
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
