"""
HTML report: semantic violation rate, DIM refund cap, suspension, ticket history.

Data source: ``StorageBundle.decision_audit`` (regenerable offline via ``__main__``).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
_SAMPLE_DIR = Path(__file__).resolve().parent
for _p in (_SRC, _SAMPLES, _SAMPLE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core import AgentRegistry
from dir_core.storage import StorageBundle

from pipeline import SimulationResult, SimulationStep, rolling_violation_series


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _new_report_path(sample_dir: Path, slug: str = "semantic_refund") -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    suffix = f"_{slug}" if slug else ""
    return results_dir / f"report_{stamp}{suffix}.html"


def _format_y_tick_pct(v: float) -> str:
    if abs(v - round(v)) < 0.05:
        return f"{int(round(v))}%"
    return f"{v:.1f}%"


def _x_tick_indices(n: int) -> List[int]:
    if n <= 0:
        return []
    if n == 1:
        return [0]
    if n <= 12:
        return sorted({0, n - 1, *range(0, n, max(1, n // 3))})
    return sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})


def _svg_refund_and_violation_charts(
    refund_eur: List[float],
    violation_rates: List[Optional[float]],
    *,
    window: int,
    threshold: float,
    suspension_idx: Optional[int],
    max_refund_eur: float,
    min_delay_hours: float,
    width: int = 900,
    height: int = 560,
) -> str:
    if not refund_eur or len(refund_eur) != len(violation_rates):
        return '<p class="muted">No executed refunds to plot.</p>'
    n = len(refund_eur)
    pct_series = [(v * 100.0) if v is not None else None for v in violation_rates]
    rates_defined = [v for v in violation_rates if v is not None]
    thr_pct = threshold * 100.0

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

    vmax_eur = max(max_refund_eur, max(refund_eur) if refund_eur else 0.0) * 1.12
    vmin_eur = 0.0

    def y_eur(e: float) -> float:
        return y_top1 - (e - vmin_eur) / (vmax_eur - vmin_eur) * h_top

    vmax_pct = 100.0
    if rates_defined:
        vmax_pct = max(
            100.0,
            max(r * 100.0 for r in rates_defined) * 1.2,
            thr_pct * 1.15,
        )
    vmin_pct = 0.0

    def y_pct(p: float) -> float:
        return y_bot1 - (p - vmin_pct) / (vmax_pct - vmin_pct) * h_bot

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'class="chart" role="img" aria-label="Refund amounts and rolling violation rate">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="var(--bg)" rx="6"/>',
        f'<text x="{width / 2:.0f}" y="22" text-anchor="middle" fill="var(--fg)" '
        f'font-size="15" font-weight="600">Figure 1 — Executed refunds and compliance monitor</text>',
        f'<text x="{width / 2:.0f}" y="40" text-anchor="middle" fill="var(--muted)" '
        f'font-size="11">Horizontal axis: refund execution order (1 = first refund in this run)</text>',
        f'<text x="{left:.0f}" y="{y_top0 - 6:.0f}" text-anchor="start" fill="var(--fg)" '
        f'font-size="12" font-weight="600">A. Refund amount per execution (DIM ceiling: '
        f'{max_refund_eur:.0f} EUR)</text>',
        f'<line x1="{left}" y1="{y_top1}" x2="{right}" y2="{y_top1}" '
        'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
        f'<line x1="{left}" y1="{y_top0}" x2="{left}" y2="{y_top1}" '
        'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
    ]
    y_cap = y_eur(max_refund_eur)
    if y_top0 <= y_cap <= y_top1:
        parts.append(
            f'<line x1="{left}" y1="{y_cap:.1f}" x2="{right}" y2="{y_cap:.1f}" '
            'stroke="#6e7681" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.9"/>'
            f'<text x="{right - 4:.1f}" y="{max(y_cap - 6, y_top0 + 10):.1f}" text-anchor="end" '
            f'fill="#6e7681" font-size="10">DIM max {max_refund_eur:.0f} EUR</text>'
        )
    for yv, lab in (
        (vmin_eur, "0"),
        (vmax_eur / 2, f"{vmax_eur / 2:.0f}"),
        (vmax_eur, f"{vmax_eur:.0f}"),
    ):
        yy = y_eur(yv)
        parts.append(
            f'<line x1="{left - 4}" y1="{yy:.1f}" x2="{left}" y2="{yy:.1f}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.35"/>'
            f'<text x="{left - 6:.1f}" y="{yy + 4:.1f}" text-anchor="end" fill="var(--muted)" '
            f'font-size="10">EUR {lab}</text>'
        )
    bar_w = max(2.0, wplot / max(n * 1.8, 1))
    for i, amt in enumerate(refund_eur):
        xc = x_for(i)
        y0 = y_eur(0.0)
        y1 = y_eur(amt)
        x0 = xc - bar_w / 2
        parts.append(
            f'<rect x="{x0:.1f}" y="{min(y0, y1):.1f}" width="{bar_w:.1f}" '
            f'height="{abs(y1 - y0):.1f}" fill="var(--info)" opacity="0.85" rx="1"/>'
        )

    parts.extend(
        [
            f'<text x="{left:.0f}" y="{y_bot0 - 8:.0f}" text-anchor="start" fill="var(--fg)" '
            f'font-size="12" font-weight="600">B. Rolling policy violation rate (last {window} '
            f"refunds)</text>",
            f'<text x="{left:.0f}" y="{y_bot0 + 6:.0f}" text-anchor="start" fill="var(--muted)" '
            f'font-size="10">Numerator: refunds where delay ≤ {min_delay_hours:.0f}h (refund should '
            f"not have been issued). Denominator: {window}. Empty left region: fewer than {window} "
            f"refunds yet — rate undefined.</text>",
            f'<line x1="{left}" y1="{y_bot1}" x2="{right}" y2="{y_bot1}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
            f'<line x1="{left}" y1="{y_bot0}" x2="{left}" y2="{y_bot1}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.5"/>',
        ]
    )

    first_rate_i = next((i for i, v in enumerate(pct_series) if v is not None), n)
    if first_rate_i > 0:
        x_warm_end = (x_for(first_rate_i - 1) + x_for(first_rate_i)) / 2.0
        cx_w = (left + x_warm_end) / 2.0
        cy_w = (y_bot0 + y_bot1) / 2.0
        parts.append(
            f'<rect x="{left:.1f}" y="{y_bot0:.1f}" width="{x_warm_end - left:.1f}" '
            f'height="{h_bot:.1f}" fill="#30363d" opacity="0.45"/>'
            f'<text x="{cx_w:.0f}" y="{cy_w - 6:.0f}" text-anchor="middle" '
            f'fill="var(--muted)" font-size="10">Warm-up</text>'
            f'<text x="{cx_w:.0f}" y="{cy_w + 8:.1f}" text-anchor="middle" '
            f'fill="var(--muted)" font-size="10">(&lt; {window} refunds)</text>'
        )

    if vmin_pct <= thr_pct <= vmax_pct:
        y_thr = y_pct(thr_pct)
        parts.append(
            f'<line x1="{left}" y1="{y_thr:.1f}" x2="{right}" y2="{y_thr:.1f}" '
            'stroke="var(--warn)" stroke-width="1.35" stroke-dasharray="5 4" opacity="0.92"/>'
            f'<text x="{right - 4:.1f}" y="{y_thr - 5:.1f}" text-anchor="end" fill="var(--warn)" '
            f'font-size="10" font-weight="500">Suspend if rate &gt; {thr_pct:.0f}%</text>'
        )

    for yv in (vmin_pct, (vmin_pct + vmax_pct) / 2, vmax_pct):
        yy = y_pct(yv)
        parts.append(
            f'<line x1="{left - 4}" y1="{yy:.1f}" x2="{left}" y2="{yy:.1f}" '
            'stroke="var(--muted)" stroke-width="1" opacity="0.35"/>'
            f'<text x="{left - 6:.1f}" y="{yy + 4:.1f}" text-anchor="end" fill="var(--muted)" '
            f'font-size="10">{_format_y_tick_pct(yv)}</text>'
        )

    ma_pts: List[str] = []
    for i, p in enumerate(pct_series):
        if p is not None:
            ma_pts.append(f"{x_for(i):.1f},{y_pct(p):.1f}")
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
        f'fill="var(--fg)" font-size="12" font-weight="500">Refund execution index (chronological)</text>'
    )

    if suspension_idx is not None and 0 <= suspension_idx < n:
        sx = x_for(suspension_idx)
        parts.append(
            f'<line x1="{sx:.1f}" y1="{y_top0}" x2="{sx:.1f}" y2="{y_bot1}" '
            'stroke="var(--reject)" stroke-width="2" stroke-dasharray="5 4" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{min(sx + 8, right - 80):.1f}" y="{y_top0 + 12:.1f}" text-anchor="start" '
            f'fill="var(--reject)" font-size="11" font-weight="700">Run stopped — agent suspended</text>'
        )
        susp_v = pct_series[suspension_idx]
        if susp_v is not None:
            sy = y_pct(susp_v)
            parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6" fill="var(--reject)" stroke="var(--bg)" '
                'stroke-width="2"/>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _legend_block(window: int, threshold_pct: float) -> str:
    return f"""
    <ul class="chart-legend" aria-label="Chart legend">
      <li><span class="swatch bar-blue"></span> Panel A: refund amount (each bar = one executed refund)</li>
      <li><span class="swatch zone-warm"></span> Panel B: warm-up (violation rate not computed yet)</li>
      <li><span class="swatch line-purple"></span> Panel B: rolling violation share (last {window} refunds)</li>
      <li><span class="swatch line-warn"></span> Suspension threshold ({threshold_pct:.0f}% of recent refunds)</li>
      <li><span class="swatch line-suspend"></span> Red vertical line: last refund before suspension</li>
    </ul>
    """


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
            acc["delay_hours"] = float(d.get("delay_hours", 0.0))
            acc["order_ref"] = str(d.get("order_ref", ""))
            acc["channel"] = str(d.get("channel", ""))
            acc["subject"] = str(d.get("subject", ""))
            acc["message_preview"] = str(d.get("message_preview", ""))
        elif et == "NO_REFUND_PROPOSAL":
            acc["dim_verdict"] = "—"
            acc["dim_reason"] = str(d.get("reason", "No proposal"))
        elif et == "POLICY_PROPOSAL":
            acc["refund_amount_eur"] = float(d.get("refund_amount_eur", 0.0))
        elif et == "DIM_VALIDATION":
            acc["dim_verdict"] = str(e.get("state") or "")
            acc["dim_reason"] = str(d.get("reason", ""))
        elif et == "REFUND_EXECUTED":
            acc["executed"] = True
            acc["refund_amount_eur"] = float(
                d.get("refund_amount_eur", acc.get("refund_amount_eur", 0.0))
            )
            acc["delay_hours"] = float(d.get("delay_hours", acc.get("delay_hours", 0.0)))
        elif et == "MONITOR_TICK" and d.get("violation_rate") is not None:
            acc["violation_rate_after"] = float(d["violation_rate"])

    steps: List[SimulationStep] = []
    for i, dfid in enumerate(order):
        a = by_dfid[dfid]
        steps.append(
            SimulationStep(
                iteration=i,
                dfid=dfid,
                input_ref=str(a.get("input_ref", "")),
                order_ref=str(a.get("order_ref", "")),
                channel=str(a.get("channel", "")),
                delay_hours=float(a.get("delay_hours", 0.0)),
                subject=str(a.get("subject", "")),
                message_preview=str(a.get("message_preview", "")),
                refund_amount_eur=a.get("refund_amount_eur"),
                dim_verdict=str(a.get("dim_verdict", "")),
                dim_reason=str(a.get("dim_reason", "")),
                executed=bool(a.get("executed")),
                violation_rate_after=a.get("violation_rate_after"),
                console_note="",
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
        break

    return SimulationResult(
        steps=steps,
        stopped_reason=stopped,
        total_inputs=total_inputs,
        suspension_decision_number=suspension_decision_number,
    )


def generate_report(
    sample_dir: Path,
    bundle: StorageBundle,
    *,
    simulation_id: str,
    window: int,
    agent_id: str,
    registry_status: Optional[tuple] = None,
    max_refund_eur: float,
    violation_threshold: float,
    min_delay_hours: float,
    normal_phase_iterations: int,
    llm_backend: str = "Mock",
    slug: str = "",
) -> Path:
    """Build HTML from ``decision_audit.all_events_chronological()`` (§17.3)."""
    events = bundle.decision_audit.all_events_chronological()
    sim = hydrate_simulation_result(events, simulation_id)
    slug_use = slug or "semantic_refund"
    out = _new_report_path(sample_dir, slug=slug_use)

    ma_series = rolling_violation_series(
        bundle,
        simulation_id,
        window,
        min_delay_hours_exclusive=min_delay_hours,
    )

    exec_steps = [s for s in sim.steps if s.executed]
    suspended = sim.stopped_reason == "semantic_compliance_monitor"
    suspend_idx = len(exec_steps) - 1 if suspended and exec_steps else None

    ma_aligned: List[Optional[float]] = []
    if len(ma_series) >= len(exec_steps):
        ma_aligned = list(ma_series[: len(exec_steps)])
    else:
        ma_aligned = [*ma_series, *([None] * (len(exec_steps) - len(ma_series)))]

    refund_amounts = [
        float(s.refund_amount_eur)
        for s in exec_steps
        if s.refund_amount_eur is not None
    ]
    if len(refund_amounts) != len(ma_aligned):
        refund_amounts = [float(s.refund_amount_eur or 0.0) for s in exec_steps]

    chart_main = (
        '<figure class="chart-wrap" aria-label="Refund amounts and rolling violation rate">'
        + _svg_refund_and_violation_charts(
            refund_amounts,
            ma_aligned,
            window=window,
            threshold=violation_threshold,
            suspension_idx=suspend_idx,
            max_refund_eur=max_refund_eur,
            min_delay_hours=min_delay_hours,
        )
        + _legend_block(window, violation_threshold * 100.0)
        + "</figure>"
    )

    thr_pct = violation_threshold * 100.0
    experiment_block = f"""
  <div class="panel experiment">
    <h2>What this experiment demonstrates</h2>
    <p>This sample illustrates <strong>semantic drift</strong> in a shipping-refund workflow.
       The business rule is strict: issue a <strong>goodwill refund only when the recorded
       delay exceeds {min_delay_hours:.0f} hours</strong>. The agent contract caps any single
       refund at <strong>{max_refund_eur:.0f} EUR</strong>.</p>
    <p>The <strong>Decision Integrity Module (DIM)</strong> enforces only what is encoded in
       the kernel contract (here: amount ≤ {max_refund_eur:.0f} EUR, schema, RBAC, TTL). It does
       <em>not</em> evaluate whether the shipment delay exceeded {min_delay_hours:.0f} hours.
       Therefore the agent can remain “kernel-compliant” while systematically breaking policy
       intent — for example by approving refunds after empathy-biased reading of emotional
       customer messages.</p>
    <p><strong>Simulation design:</strong> Early tickets (roughly the first
       {normal_phase_iterations} support rows in the input file) use delays above the threshold
       and neutral operational language; the simulated agent only refunds when the delay rule is
       satisfied. After that phase, the same agent model may refund shorter delays when messages
       contain configured emotional triggers. Those refunds still pass DIM, but they are
       <strong>semantic violations</strong> (refund issued while delay ≤ {min_delay_hours:.0f}h).</p>
    <p><strong>ComplianceMonitor:</strong> After each executed refund, canonical telemetry rows
       (<code>REFUND_EXECUTED</code> in <code>decision_audit_events</code>) carry
       <code>delay_hours</code>. The monitor computes the share of the last <strong>{window}</strong>
       refunds that violated the delay rule. If that share exceeds <strong>{thr_pct:.0f}%</strong>, the
       agent is moved to <code>SUSPENDED</code> with reason <code>SEMANTIC_RULE_VIOLATION_DRIFT</code>.</p>
    <p><strong>How to read Figure 1:</strong> Panel A shows every refund the runtime actually
       executed. Panel B shows the rolling violation rate; the shaded <em>warm-up</em> region is expected
       — the rate is undefined until at least {window} refunds exist.</p>
  </div>
"""

    rows_html = []
    for s in sim.steps:
        vr = s.violation_rate_after
        vr_s = f"{vr * 100:.1f}%" if vr is not None else "—"
        ref_s = f"{s.refund_amount_eur:.0f}" if s.refund_amount_eur is not None else "—"
        dim_badge = (
            "ok" if s.dim_verdict == "ACCEPT" else (
                "reject" if s.dim_verdict == "REJECT" else "muted"
            )
        )
        rows_html.append(
            "<tr>"
            f"<td>{s.iteration + 1}</td>"
            f'<td><code title="{_esc(s.dfid)}">{_esc(s.dfid[:8])}...</code></td>'
            f"<td>{_esc(s.input_ref)}</td>"
            f"<td><code>{_esc(s.order_ref)}</code></td>"
            f"<td>{_esc(s.channel)}</td>"
            f"<td>{s.delay_hours:.1f}</td>"
            f"<td>{_esc(s.subject)}</td>"
            f'<td class="reason" title="{_esc(s.message_preview)}">{_esc(s.message_preview)}</td>'
            f"<td>{ref_s}</td>"
            f'<td><span class="badge {dim_badge}">{_esc(s.dim_verdict)}</span></td>'
            f"<td>{'yes' if s.executed else 'no'}</td>"
            f"<td>{vr_s}</td>"
            f"<td>{_esc(s.console_note or '')}</td>"
            "</tr>"
        )

    status_s = "—"
    reason_s = "—"
    rs = registry_status
    if rs is None:
        reg = AgentRegistry(storage=bundle.agent_registry, supported_versions="1.x")
        rs = reg.get_agent_status(agent_id)
    if rs:
        status_s = _esc(rs[0])
        reason_s = _esc(rs[1] or "")

    if sim.suspension_decision_number is not None:
        susp_block = (
            f'<div class="panel susp">'
            f"<h2>Agent suspension</h2>"
            f"<p>After ticket <strong>#{sim.suspension_decision_number}</strong>, "
            f"the ComplianceMonitor detected rolling semantic violation rate above "
            f"<strong>{thr_pct:.0f}%</strong> among the last refunds. "
            f"The registry moved <code>{_esc(agent_id)}</code> to "
            f"<strong>SUSPENDED</strong> (reason: {_esc(reason_s)}).</p>"
            f"</div>"
        )
    else:
        susp_block = (
            '<div class="panel"><h2>Agent suspension</h2>'
            '<p class="muted">No suspension in this run (all inputs processed or other stop).</p>'
            "</div>"
        )

    monitor_rows = [
        e
        for e in events
        if (e.get("details") or {}).get("simulation_id") == simulation_id
        and str(e.get("event") or "") in ("MONITOR_TICK", "AGENT_SUSPENDED")
    ]
    mon_lines = []
    for ev in monitor_rows[-12:]:
        det = json.dumps(ev.get("details") or {}, sort_keys=True, default=str)
        mon_lines.append(
            f"<li><code>{_esc(ev.get('event'))}</code> {_esc(ev.get('state'))} "
            f"— {_esc(det)}</li>"
        )
    mon_section = (
        '<h2>Monitor events (tail)</h2><ul class="muted">'
        + ("".join(mon_lines) if mon_lines else "<li>None</li>")
        + "</ul>"
    )

    n_events_run = sum(
        1
        for e in events
        if (e.get("details") or {}).get("simulation_id") == simulation_id
    )
    summary_panel = f"""
  <div class="panel summary">
    <h2>Run summary</h2>
    <p class="muted">Sample 37 — classic — {_esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}
       — LLM backend: {_esc(llm_backend)}</p>
    <p><code>simulation_id</code>: {_esc(simulation_id)}</p>
    <p>Telemetry rows (this run): {n_events_run} — steps in table: {len(sim.steps)}</p>
  </div>
"""

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Sample 37 - Semantic refund drift</title>
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
    }}
    body {{
      font-family: system-ui, sans-serif;
      background: #010409;
      color: var(--fg);
      margin: 0;
      padding: 2rem;
      line-height: 1.5;
    }}
    main {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{ font-size: 1.35rem; }}
    h2 {{ font-size: 1.05rem; margin-top: 1.5rem; }}
    .badge.ok {{ color: var(--ok); font-weight: 600; }}
    .badge.reject {{ color: var(--reject); font-weight: 600; }}
    .badge.muted {{ color: var(--muted); }}
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
      max-width: 18rem;
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
    .swatch.line-warn {{ border-color: var(--warn); border-style: dashed; width: 1.6rem; }}
    .swatch.line-suspend {{ border-color: var(--reject); border-style: dashed; width: 1.6rem; }}
    .swatch.line-purple {{ border-color: #a371f7; width: 1.6rem; }}
    .panel {{
      background: #161b22;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem 1.25rem;
      margin: 1rem 0;
    }}
    .panel.susp {{ border-color: var(--reject); }}
    .panel.experiment h2 {{ margin-top: 0; }}
    .panel.experiment p {{ margin: 0.65rem 0 0 0; }}
    .panel.experiment p:first-of-type {{ margin-top: 0; }}
    .swatch.bar-blue {{
      width: 1rem;
      height: 0.65rem;
      border: none;
      border-radius: 2px;
      background: var(--info);
      border-bottom: none;
    }}
    .swatch.zone-warm {{
      width: 1rem;
      height: 0.65rem;
      border: none;
      border-radius: 2px;
      background: #30363d;
      border-bottom: none;
    }}
    .swatch.line-purple {{ border-color: #a371f7; width: 1.6rem; }}
  </style>
</head>
<body>
<main>
  <h1>Sample 37 — Semantic drift (shipping refunds)</h1>
  {summary_panel}
  <p class="muted">Run outcome: <strong>{_esc(sim.stopped_reason)}</strong>.
     Support tickets processed as steps: {len(sim.steps)} / {sim.total_inputs}.</p>

  {experiment_block}

  <div class="panel">
    <p><strong>Agent</strong> {_esc(agent_id)}</p>
    <p><strong>Registry status</strong> {status_s}
       &nbsp;|&nbsp; <strong>Suspension reason</strong> {reason_s}</p>
    <p><strong>Hard limit (DIM)</strong> max_refund_eur =
       {max_refund_eur:.1f} EUR
       &nbsp;|&nbsp; <strong>Business rule (monitor)</strong> refund only if delay &gt; {min_delay_hours:.0f}h
       &nbsp;|&nbsp; <strong>Monitor threshold</strong> rolling {window}
       refunds with violation rate &gt; {thr_pct:.0f}%</p>
  </div>

  {susp_block}

  <h2>Figure 1 — Refunds and rolling violation rate</h2>
  <p class="muted">Panel A: executed refund amounts. Panel B: rolling semantic violation rate.</p>
  {chart_main}

  {mon_section}

  <h2>Ticket-level trace</h2>
  <p class="muted">Source: <code>data/support_tickets.json</code>. Column
     <strong>Viol. rate</strong> shows the rolling violation share after each executed refund;
     em dash (—) means fewer than {window} refunds yet.</p>
  <table>
    <thead>
      <tr>
        <th>#</th><th>DFID</th><th>Ticket</th><th>Order</th><th>Channel</th><th>Delay h</th><th>Subject</th>
        <th>Message (preview)</th><th>Refund EUR</th>
        <th>DIM</th><th>Executed</th><th title="Rolling violation rate after refund; — = warm-up">Viol. rate</th><th>Note</th>
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


if __name__ == "__main__":
    from shared.bootstrap import setup_environment

    from mocks import make_mock_strategy
    from schemas import (  # type: ignore[attr-defined]
        load_refund_full_config,
        load_refund_sample_config_bundle,
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
    config = load_refund_full_config(sample_dir)
    cfg = load_refund_sample_config_bundle(sample_dir)

    env = setup_environment(
        config,
        mock_llm_strategy=make_mock_strategy(seed=cfg.simulation.simulation_seed),
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
    st = AgentRegistry(
        storage=bundle.agent_registry,
        supported_versions=cfg.registry.supported_versions,
    ).get_agent_status(agent_id)
    out = generate_report(
        sample_dir,
        bundle,
        simulation_id=resolved,
        window=cfg.monitor.window_size,
        agent_id=agent_id,
        registry_status=st,
        max_refund_eur=cfg.contract.max_refund_eur,
        violation_threshold=cfg.monitor.violation_rate_threshold,
        min_delay_hours=cfg.monitor.min_delay_hours_for_refund,
        normal_phase_iterations=cfg.simulation.normal_phase_iterations,
        llm_backend="offline",
    )
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(args.output_path)
    else:
        print(out)
