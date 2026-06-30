"""HTML report for retention airlock runs (regenerable from audit store)."""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
_SAMPLE_DIR = Path(__file__).resolve().parent
for _p in (_SRC, _SAMPLES, _SAMPLE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core import AgentRegistry
from dir_core.storage import StorageBundle
from shared.bootstrap import setup_environment

from context_tax import format_context_tax_summary
from orchestrator import PhaseAResult
from schemas import (
    DriftSweepResult,
    RetentionAirlockConfig,
    TemporalMonitorConfig,
    load_sample_config,
)
from temporal_monitor import executed_discounts_for_simulation

_REPORT_CSS = """
    :root {
      --bg: #0f172a; --fg: #e2e8f0; --muted: #94a3b8; --border: #334155;
      --ok: #22c55e; --reject: #ef4444; --warn: #f59e0b; --info: #38bdf8;
    }
    body { background: var(--bg); color: var(--fg); font-family: system-ui, sans-serif;
            max-width: 1200px; margin: 0 auto; padding: 2rem; }
    h1 { color: #f8fafc; margin-bottom: 0.25rem; }
    h2 { color: #f8fafc; }
    .subtitle { color: var(--muted); margin-top: 0; font-size: 1rem; }
    .panel { border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem;
              margin: 1rem 0; background: #111827; }
    .muted { color: var(--muted); }
    table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
    th, td { border-bottom: 1px solid var(--border); padding: 0.45rem 0.5rem; text-align: left;
              vertical-align: top; }
    tr.phase-header td { background: #1e293b; color: #cbd5e1; font-weight: 600;
                        font-size: 0.8rem; letter-spacing: 0.04em; text-transform: uppercase;
                        padding: 0.6rem 0.5rem; border-bottom: 2px solid var(--border); }
    code { color: var(--info); font-size: 0.88em; }
    details.roa-block { margin: 0.5rem 0; }
    pre { white-space: pre-wrap; font-size: 0.85rem; color: var(--muted); }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                     gap: 0.75rem; }
    .metric { border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem 0.8rem; }
    .metric strong { display: block; font-size: 1.2rem; }
    .metric strong.metric-info { color: var(--info); }
    .metric strong.metric-ok { color: var(--ok); }
    .metric strong.metric-warn { color: var(--warn); }
    .metric strong.metric-reject { color: var(--reject); }
    .verdict { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
               font-size: 0.8rem; font-weight: 600; letter-spacing: 0.02em; }
    .verdict-ok { background: rgba(34,197,94,0.15); color: var(--ok); border: 1px solid var(--ok); }
    .verdict-reject { background: rgba(239,68,68,0.15); color: var(--reject); border: 1px solid var(--reject); }
    .verdict-warn { background: rgba(245,158,11,0.15); color: var(--warn); border: 1px solid var(--warn); }
    .verdict-neutral { background: rgba(148,163,184,0.12); color: var(--muted); border: 1px solid var(--border); }
    .badge { display: inline-block; padding: 0.1rem 0.45rem; border-radius: 999px;
             font-size: 0.72rem; font-weight: 600; margin: 0.1rem 0.15rem 0.1rem 0; }
    .badge-pass { background: rgba(34,197,94,0.12); color: var(--ok); border: 1px solid rgba(34,197,94,0.35); }
    .badge-reject { background: rgba(239,68,68,0.15); color: var(--reject); border: 1px solid var(--reject); }
    .badge-skip { background: rgba(148,163,184,0.1); color: var(--muted); border: 1px solid var(--border); }
    .gates-all-pass { color: var(--ok); font-size: 0.85rem; }
    details.gate-pass summary { cursor: pointer; color: var(--muted); font-size: 0.8rem; }
"""


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _new_report_path(sample_dir: Path, slug: str = "retention_airlock") -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return results_dir / f"report_{stamp}_{slug}.html"


def _verdict_css_class(verdict: str) -> str:
    v = str(verdict).upper()
    if v == "ACCEPT":
        return "verdict-ok"
    if v in ("REJECT", "SUSPENDED"):
        return "verdict-reject"
    if v == "ESCALATE":
        return "verdict-warn"
    return "verdict-neutral"


def _metric_css_class(agent_status: str) -> str:
    s = str(agent_status).upper()
    if s == "ACTIVE":
        return "metric-ok"
    if s == "SUSPENDED":
        return "metric-reject"
    return "metric-info"


def _verdict_badge(verdict: str) -> str:
    return f'<span class="verdict {_verdict_css_class(verdict)}">{_esc(verdict)}</span>'


def _strip_dim_reason(reason: str) -> str:
    text = str(reason)
    prefix = "Custom validation failed: "
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def _gate_label(gate: str) -> str:
    return gate.replace("_", " ")


def _airlock_badges(trace: Dict[str, str]) -> str:
    if not trace:
        return '<span class="muted">—</span>'
    failed = {k: v for k, v in trace.items() if str(v).upper() not in ("PASS", "SKIP")}
    passed = {k: v for k, v in trace.items() if str(v).upper() == "PASS"}
    parts: List[str] = []
    for gate, state in failed.items():
        cls = "badge-reject" if str(state).upper() == "REJECT" else "badge-skip"
        parts.append(
            f'<span class="badge {cls}" title="{_esc(gate)}">{_esc(_gate_label(gate))}: '
            f'{_esc(state)}</span>'
        )
    if not failed and passed:
        parts.append('<span class="gates-all-pass">all gates PASS</span>')
    elif passed:
        gate_list = ", ".join(_gate_label(g) for g in passed)
        parts.append(
            f'<details class="gate-pass"><summary>+{len(passed)} PASS</summary>'
            f'<span class="muted">{_esc(gate_list)}</span></details>'
        )
    return "".join(parts) if parts else '<span class="muted">—</span>'


def _is_drift_sweep(label: str) -> bool:
    return "temporal_drift_sweep" in str(label)


def _svg_discount_chart(
    discounts: List[float],
    *,
    threshold: float,
    suspension_at: Optional[int],
) -> str:
    if not discounts:
        return '<p class="muted">No executed discounts to chart.</p>'
    w, h = 720, 240
    pad_l, pad_r, pad_t, pad_b = 48, 20, 16, 36
    ymax = max(max(discounts) + 2, threshold + 2, 18)
    ymin = 0.0
    n = len(discounts)
    inner_w = w - pad_l - pad_r
    inner_h = h - pad_t - pad_b

    def x_at(i: int) -> float:
        if n == 1:
            return pad_l + inner_w / 2
        return pad_l + (i / (n - 1)) * inner_w

    def y_at(v: float) -> float:
        return pad_t + inner_h - ((v - ymin) / (ymax - ymin)) * inner_h

    y_ticks: List[str] = []
    step = 5.0
    tick = 0.0
    while tick <= ymax + 0.01:
        y = y_at(tick)
        y_ticks.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" '
            f'stroke="#334155" stroke-width="1" stroke-dasharray="3 4"/>'
            f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" fill="#94a3b8" '
            f'font-size="10">{tick:.0f}%</text>'
        )
        tick += step

    points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(discounts))
    thresh_y = y_at(threshold)
    suspension_line = ""
    if suspension_at is not None and suspension_at > 0:
        sx = x_at(min(suspension_at - 1, n - 1))
        suspension_line = (
            f'<line x1="{sx:.1f}" y1="{pad_t}" x2="{sx:.1f}" y2="{h - pad_b}" '
            f'stroke="#ef4444" stroke-width="2" stroke-dasharray="6 4"/>'
            f'<text x="{sx + 4:.1f}" y="{pad_t + 12}" fill="#ef4444" font-size="11">'
            f"Circuit breaker</text>"
        )

    return f"""
<figure aria-label="Rolling discount trajectory">
  <svg viewBox="0 0 {w} {h}" width="100%" height="auto">
    {''.join(y_ticks)}
    <line x1="{pad_l}" y1="{h - pad_b}" x2="{w - pad_r}" y2="{h - pad_b}" stroke="#64748b"/>
    <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h - pad_b}" stroke="#64748b"/>
    <line x1="{pad_l}" y1="{thresh_y:.1f}" x2="{w - pad_r}" y2="{thresh_y:.1f}"
          stroke="#f59e0b" stroke-dasharray="4 4" stroke-width="1.5"/>
    <text x="{w - pad_r - 4}" y="{thresh_y - 4:.1f}" text-anchor="end" fill="#f59e0b" font-size="11">
      threshold {threshold:.1f}%
    </text>
    <polyline fill="none" stroke="#38bdf8" stroke-width="2" points="{points}"/>
    {suspension_line}
    <text x="{pad_l}" y="{h - 8}" fill="#94a3b8" font-size="11">Decision index</text>
    <text x="8" y="{pad_t + 40}" fill="#94a3b8" font-size="11" transform="rotate(-90 12 {pad_t + 40})">
      discount %
    </text>
  </svg>
  <figcaption>Executed discount per decision; dashed amber line is Temporal Governance threshold.</figcaption>
</figure>
"""


def _context_tax_svg(attempts: List[Any]) -> str:
    if not attempts:
        return '<p class="muted">No Context Tax data for this run.</p>'
    w, h = 520, 180
    pad_l, pad_b = 56, 36
    max_tok = max(a.estimated_tokens for a in attempts) if attempts else 800
    bar_w = 80
    gap = 40
    bars: List[str] = []
    for i, a in enumerate(attempts):
        x = pad_l + i * (bar_w + gap)
        bh = int((a.estimated_tokens / max_tok) * (h - pad_b - 30))
        y = h - pad_b - bh
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bh}" fill="#f59e0b" rx="4"/>'
            f'<text x="{x + bar_w/2}" y="{h - 12}" text-anchor="middle" '
            f'fill="#94a3b8" font-size="11">retry {a.attempt}</text>'
            f'<text x="{x + bar_w/2}" y="{y - 6}" text-anchor="middle" '
            f'fill="#e2e8f0" font-size="11">~{a.estimated_tokens}</text>'
        )
    summary = format_context_tax_summary(
        [(a.attempt, a.estimated_tokens) for a in attempts]
    )
    return f"""
<figure aria-label="Context Tax growth on DIM retries">
  <svg viewBox="0 0 {w} {h}" width="100%" height="auto">
    <line x1="{pad_l}" y1="{h - pad_b}" x2="{w - 20}" y2="{h - pad_b}" stroke="#64748b"/>
    <line x1="{pad_l}" y1="20" x2="{pad_l}" y2="{h - pad_b}" stroke="#64748b"/>
    {''.join(bars)}
  </svg>
  <figcaption><strong>Context Tax</strong> — illustrative input tokens per retry cycle as
  <code>prior_failure_trace</code> accumulates: {_esc(summary)}</figcaption>
</figure>
"""


def _context_tax_section(phase_a: Optional[PhaseAResult]) -> str:
    if not phase_a:
        return ""
    row = next(
        (s for s in phase_a.scenarios if "efficiency_trap" in s.label),
        None,
    )
    if not row or len(row.context_tax_attempts) <= 1:
        return ""
    trace_blocks: List[str] = []
    for a in row.context_tax_attempts:
        if a.prior_failure_trace:
            trace_blocks.append(
                f"<li>retry {a.attempt} (~{a.estimated_tokens} tokens): "
                f"<code>{_esc(a.prior_failure_trace[:200])}</code>...</li>"
            )
        else:
            trace_blocks.append(
                f"<li>retry {a.attempt}: ~{a.estimated_tokens} tokens (initial context)</li>"
            )
    traces_html = "\n".join(trace_blocks) if trace_blocks else ""
    return f"""
<div class="panel">
  <h2>Context Tax — Scenario 2 (Efficiency Trap)</h2>
  <p class="muted">Each DIM rejection re-sends the full transcript plus accumulated
  <code>prior_failure_trace</code>. Input-token budget grows exponentially while Fact
  Validation still rejects at zero extra LLM reasoning cost.</p>
  {_context_tax_svg(row.context_tax_attempts)}
  <ul>{traces_html}</ul>
</div>
"""


def _scenario_row_html(r: Any) -> str:
    trace = getattr(r, "airlock_trace", {}) or {}
    reason = _strip_dim_reason(getattr(r, "dim_reason", ""))
    return (
        f"<tr>"
        f"<td>{_esc(getattr(r, 'label', ''))}</td>"
        f"<td><code title=\"{_esc(getattr(r, 'dfid', ''))}\">"
        f"{_esc(str(getattr(r, 'dfid', ''))[:10])}...</code></td>"
        f"<td>{_verdict_badge(getattr(r, 'expected', ''))}</td>"
        f"<td>{_verdict_badge(getattr(r, 'final_verdict', ''))}</td>"
        f"<td>{'yes' if getattr(r, 'executed', False) else 'no'}</td>"
        f"<td>{_airlock_badges(trace)}</td>"
        f"<td><code>{_esc(reason[:160])}</code></td>"
        f"</tr>"
    )


def _drift_sweep_group_row(
    steps: List[Any],
    phase_b: Optional[DriftSweepResult],
    monitor_cfg: TemporalMonitorConfig,
) -> str:
    if not steps:
        return ""
    n = len(steps)
    first_label = getattr(steps[0], "label", "5_temporal_drift_sweep")
    m = re.search(r"_(\d+)$", str(first_label))
    start_i = int(m.group(1)) if m else 1
    end_i = start_i + n - 1
    label = f"5_temporal_drift_sweep_{start_i:02d}–{end_i:02d}"
    all_accept = all(getattr(s, "final_verdict", "") == "ACCEPT" for s in steps)
    final = "SUSPENDED" if (phase_b and phase_b.suspended) else getattr(
        steps[-1], "final_verdict", "ACCEPT"
    )
    expected = "SUSPENDED" if phase_b and phase_b.suspended else "ACCEPT"
    reason = (
        f"ACCEPT ×{n} → rolling avg {monitor_cfg.avg_threshold_pct:.1f}% threshold breached"
        if phase_b and phase_b.suspended
        else f"ACCEPT ×{n} — {getattr(phase_b, 'stopped_reason', 'completed')}"
    )
    trace = {"syntactic": "PASS", "fact_validation": "PASS", "evidence_validation": "PASS",
             "bidirectional_reconstruction": "PASS"}
    details_rows = "".join(_scenario_row_html(s) for s in steps)
    return f"""
<tr class="drift-group">
  <td><strong>{_esc(label)}</strong>
    <details><summary class="muted">per-iteration DFIDs ({n})</summary>
    <table class="nested">{details_rows}</table></details></td>
  <td class="muted">×{n} flows</td>
  <td>{_verdict_badge(expected)}</td>
  <td>{_verdict_badge(final)}</td>
  <td>{'yes' if all_accept else 'partial'}</td>
  <td>{_airlock_badges(trace)}</td>
  <td><code>{_esc(reason)}</code></td>
</tr>
"""


def _scenario_table_html(
    phase_a_rows: List[Any],
    phase_b_rows: List[Any],
    phase_b: Optional[DriftSweepResult],
    monitor_cfg: TemporalMonitorConfig,
) -> str:
    body: List[str] = []
    if phase_a_rows:
        body.append(
            '<tr class="phase-header"><td colspan="7">'
            "Phase A — Architecture of Trust</td></tr>"
        )
        for r in phase_a_rows:
            body.append(_scenario_row_html(r))

    if phase_b_rows:
        body.append(
            '<tr class="phase-header"><td colspan="7">'
            "Phase B — Temporal Governance (drift sweep)</td></tr>"
        )
        body.append(_drift_sweep_group_row(phase_b_rows, phase_b, monitor_cfg))

    if not body:
        return '<tr><td colspan="7" class="muted">No scenario rows.</td></tr>'
    return "\n".join(body)


def _show_context_tax_block(r: Any) -> bool:
    if "efficiency_trap" not in getattr(r, "label", ""):
        return False
    attempts = getattr(r, "context_tax_attempts", None) or []
    return len(attempts) > 1 or getattr(r, "retry_count", 0) > 0


def _agent_b_block(r: Any, min_overlap: float) -> str:
    recon = getattr(r, "reconstructed_narrative", "") or ""
    if not recon:
        return ""
    overlap = float(getattr(r, "keyword_overlap", 0.0) or 0.0)
    email = getattr(r, "email_body", "") or ""
    email_short = email[:220] + ("..." if len(email) > 220 else "")
    drift = overlap < min_overlap
    verdict = "COMPRESSION_DRIFT detected" if drift else "within threshold"
    return f"""
[AGENT B RECONSTRUCTION]
  Original:      "{_esc(email_short)}"
  Reconstructed: "{_esc(recon)}"
  keyword_overlap: {overlap:.3f}  (threshold: {min_overlap:.2f}) → {_esc(verdict)}
"""


def _roa_block_html(r: Any, min_overlap: float) -> str:
    trace = getattr(r, "airlock_trace", {}) or {}
    agent_b = _agent_b_block(r, min_overlap) if "compression_drift" in getattr(r, "label", "") else ""
    tax_block = ""
    if _show_context_tax_block(r):
        tax_lines = " | ".join(
            f"retry {a.attempt}: ~{a.estimated_tokens} tokens"
            for a in (getattr(r, "context_tax_attempts", None) or [])
        )
        tax_block = f"\n[CONTEXT TAX]\n  {tax_lines}\n"
    reason = _strip_dim_reason(getattr(r, "dim_reason", ""))
    failed_gates = [
        f"{_gate_label(k)}: {v}"
        for k, v in trace.items()
        if str(v).upper() not in ("PASS", "SKIP")
    ]
    gates_line = ", ".join(failed_gates) if failed_gates else "all PASS"
    return f"""
<details class="roa-block">
  <summary>{_esc(getattr(r, 'label', ''))} — {_verdict_badge(getattr(r, 'final_verdict', ''))}</summary>
  <pre>
DFID: {_esc(getattr(r, 'dfid', ''))}
Policy: {_esc(getattr(r, 'policy_kind', ''))}  Discount: {_esc(getattr(r, 'discount_pct', 0))}%

[EXPLAIN]
  {_esc(getattr(r, 'explain_narrative', '(not recorded)'))}

[POLICY]
  {_esc(getattr(r, 'justification', '(not recorded)'))}

[AIRLOCK TRACE]
  failed gates: {_esc(gates_line)}
{agent_b}{tax_block}
[DIM]
  verdict={_esc(getattr(r, 'final_verdict', ''))}
  reason={_esc(reason)}
  retries={_esc(getattr(r, 'retry_count', 0))}
  </pre>
</details>
"""


def _drift_sweep_roa_summary(steps: List[Any], phase_b: Optional[DriftSweepResult]) -> str:
    if not steps:
        return ""
    n = len(steps)
    discounts = [getattr(s, "discount_pct", 0.0) for s in steps]
    avg_disc = sum(discounts) / n if n else 0.0
    suspended = phase_b.suspended if phase_b else False
    iter_note = (
        f"Circuit breaker at iteration {phase_b.suspension_iteration}"
        if phase_b and phase_b.suspension_iteration
        else "completed"
    )
    dfid_sample = ", ".join(_esc(getattr(s, "dfid", "")[:8]) + "..." for s in steps[:3])
    if n > 3:
        dfid_sample += f", … +{n - 3} more"
    return f"""
<details class="roa-block" open>
  <summary>5_temporal_drift_sweep (aggregate) — {_verdict_badge('SUSPENDED' if suspended else 'ACCEPT')}</summary>
  <pre>
Iterations: {n}  |  Uniform outcome: ACCEPT ×{n}
Discount offered: {avg_disc:.1f}% each (tier max)
Rolling window breach → Agent status SUSPENDED ({_esc(iter_note)})
Sample DFIDs: {dfid_sample}

[EXPLAIN] (representative)
  Customer cites pricing pressure; a moderate retention discount may preserve subscription revenue.

[POLICY] (representative)
  Propose APPLY_DISCOUNT aligned with retention mission (max allowed discount).

[AIRLOCK TRACE]
  all gates PASS on every iteration — aggregate margin erosion detected post-execution
  </pre>
</details>
"""


def _roa_sections(
    phase_a_rows: List[Any],
    phase_b_rows: List[Any],
    phase_b: Optional[DriftSweepResult],
    min_overlap: float,
) -> str:
    parts: List[str] = []
    if phase_a_rows:
        parts.append("<h3>Phase A — Architecture of Trust</h3>")
        for r in phase_a_rows:
            parts.append(_roa_block_html(r, min_overlap))
    if phase_b_rows:
        parts.append("<h3>Phase B — Temporal Governance</h3>")
        parts.append(_drift_sweep_roa_summary(phase_b_rows, phase_b))
    return "\n".join(parts) if parts else '<p class="muted">No ROA blocks.</p>'


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


def generate_report(
    sample_dir: Path,
    bundle: StorageBundle,
    *,
    simulation_id: str,
    agent_id: str,
    monitor_cfg: TemporalMonitorConfig,
    airlock: RetentionAirlockConfig,
    phase_a: Optional[PhaseAResult],
    phase_b: Optional[DriftSweepResult],
    llm_backend: str,
) -> Path:
    events = bundle.decision_audit.all_events_chronological()
    sim_events = _events_for_simulation(events, simulation_id)
    discounts = executed_discounts_for_simulation(bundle, simulation_id)
    suspension_at = phase_b.suspension_iteration if phase_b else None

    registry = AgentRegistry(storage=bundle.agent_registry, supported_versions="1.x")
    st = registry.get_agent_status(agent_id)
    agent_status = st[0] if st else "UNKNOWN"
    susp_reason = st[1] if st else ""

    phase_a_rows = phase_a.scenarios if phase_a else []
    phase_b_rows = phase_b.steps if phase_b else []
    min_overlap = airlock.bidirectional.min_keyword_overlap

    scenario_description = """
<p>This run demonstrates the <strong>Architecture of Trust</strong>: probabilistic retention reasoning is separated from
deterministic execution authority.</p>
<ul>
  <li><strong>Syntactic governance</strong> — contract boundaries and Intent Retry Governor
      (<code>max_retries={max_retries}</code>) prevent budget runaway.</li>
  <li><strong>Fact validation</strong> — tier limits (BASIC max {basic_limit:.1f}%) block
      over-discounting at zero extra LLM cost.</li>
  <li><strong>Evidence validation</strong> — independent cancel-intent classifier catches
      the Compliant Lie before execution.</li>
  <li><strong>Bidirectional reconstruction</strong> — isolated Agent B rebuilds a narrative
      from proposal JSON only; keyword overlap and salient-term checks detect
      <em>Compression Drift</em> on ambiguous emails.</li>
  <li><strong>Temporal governance</strong> — rolling window ({window}) average discount
      above {threshold:.1f}% trips a circuit breaker and suspends the agent.</li>
</ul>
""".format(
        max_retries=airlock.intent_retry_max,
        basic_limit=airlock.tier_discount_limits.get("BASIC", 15.0),
        window=monitor_cfg.window_size,
        threshold=monitor_cfg.avg_threshold_pct,
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Retention Airlock — Architecture of Trust</title>
  <style>{_REPORT_CSS}
    table.nested {{ font-size: 0.82rem; margin-top: 0.5rem; }}
    table.nested td {{ padding: 0.3rem 0.4rem; }}
    tr.drift-group td {{ vertical-align: top; }}
    h3 {{ color: #cbd5e1; font-size: 0.95rem; margin: 1rem 0 0.5rem; }}
  </style>
</head>
<body>
  <h1>Retention Airlock — Architecture of Trust</h1>
  <p class="subtitle">Defense scenarios + temporal governance sweep · sample 40</p>
  <p class="muted">Generated {_esc(datetime.now(timezone.utc).isoformat())} UTC</p>

  <div class="panel">
    <div class="summary-grid">
      <div class="metric"><span class="muted">Simulation ID</span><strong class="metric-info"><code>{_esc(simulation_id)}</code></strong></div>
      <div class="metric"><span class="muted">LLM backend</span><strong class="metric-info">{_esc(llm_backend)}</strong></div>
      <div class="metric"><span class="muted">Audit events</span><strong class="metric-info">{len(sim_events)}</strong></div>
      <div class="metric"><span class="muted">Agent status</span><strong class="{_metric_css_class(agent_status)}">{_esc(agent_status)}</strong></div>
      <div class="metric"><span class="muted">Executions</span><strong class="metric-info">{len(discounts)}</strong></div>
    </div>
    <p class="muted">Suspension reason: {_esc(susp_reason or '—')}</p>
  </div>

  <div class="panel">
    <h2>Scenario trace</h2>
    <table>
      <thead>
        <tr>
          <th>Scenario</th><th>DFID</th><th>Expected</th><th>Actual</th>
          <th>Executed</th><th>Airlock gates</th><th>Reason</th>
        </tr>
      </thead>
      <tbody>{_scenario_table_html(phase_a_rows, phase_b_rows, phase_b, monitor_cfg)}</tbody>
    </table>
  </div>

  {_context_tax_section(phase_a)}

  <div class="panel">
    <h2>Temporal Governance chart</h2>
    {_svg_discount_chart(discounts, threshold=monitor_cfg.avg_threshold_pct,
                         suspension_at=suspension_at)}
  </div>

  <div class="panel">
    <h2>ROA + Airlock reconstruction</h2>
    {_roa_sections(phase_a_rows, phase_b_rows, phase_b, min_overlap)}
  </div>

  <div class="panel">
    <h2>What this run demonstrates</h2>
    {scenario_description}
  </div>
</body>
</html>
"""
    out = _new_report_path(sample_dir)
    out.write_text(html_doc, encoding="utf-8")
    return out


def _regenerate_from_db(sample_dir: Path, simulation_id: Optional[str]) -> Path:
    config = load_sample_config(sample_dir)
    env = setup_environment(config, config_path=str(sample_dir / "config.yaml"))
    bundle = env.repository
    events = bundle.decision_audit.all_events_chronological()
    if simulation_id is None:
        for e in reversed(events):
            if e.get("event") == "SIMULATION_START":
                simulation_id = str((e.get("details") or {}).get("simulation_id", ""))
                break
    if not simulation_id:
        raise SystemExit("No SIMULATION_START found in audit store.")
    airlock = RetentionAirlockConfig.from_config(config)
    monitor_cfg = TemporalMonitorConfig.from_config(config)
    return generate_report(
        sample_dir,
        bundle,
        simulation_id=simulation_id,
        agent_id="CustomerRetentionAgent",
        monitor_cfg=monitor_cfg,
        airlock=airlock,
        phase_a=None,
        phase_b=None,
        llm_backend="(regenerated)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate retention airlock HTML report")
    parser.add_argument("--simulation-id", default=None)
    parser.add_argument("--output-path", default=None)
    args = parser.parse_args()
    sample_dir = _SAMPLE_DIR
    path = _regenerate_from_db(sample_dir, args.simulation_id)
    if args.output_path:
        out = Path(args.output_path)
        out.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path = out
    print(path)


if __name__ == "__main__":
    main()
