"""
HTML report generator for finance trading simulation.

Produces a complete audit report: price charts with decision points, DFID hierarchy,
decision details (LLM justification, DIM result), and full position lifecycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from simulation_recorder import (
    SimulationRecorder,
    TickRecord,
    SimDecisionRecord,
    PositionRecord,
)


def _escape(s: str) -> str:
    """Escape HTML special chars."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _section(title: str, content: str, expanded: bool = True) -> str:
    open_attr = "" if expanded else ' open=""'
    return f"""
    <details{open_attr}>
        <summary><strong>{_escape(title)}</strong></summary>
        <div class="section-content">{content}</div>
    </details>"""


def _build_chart_html(recorder: SimulationRecorder) -> str:
    """Build Plotly charts for each instrument: price vs tick with decision points."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return "<p><em>Chart requires plotly. Install: pip install plotly</em></p>"

    instruments = list({t.instrument for t in recorder.ticks if t.instrument})
    if not instruments:
        return "<p><em>No tick data to plot.</em></p>"

    policy_colors = {
        "HOLD": "#4ade80",
        "REDUCE": "#fbbf24",
        "CLOSE": "#f87171",
        "CLOSE_POSITION": "#f87171",
        "TAKE_PROFIT": "#fbbf24",
        "ADJUST_STOP": "#fbbf24",
        "NEWS_QUALIFIED": "#60a5fa",
        "OPEN_POSITION": "#60a5fa",
    }
    default_color = "#94a3b8"

    charts_html = []
    for idx, inst in enumerate(instruments):
        ticks_inst = [t for t in recorder.ticks if t.instrument == inst]
        if not ticks_inst:
            continue

        x_ticks = [t.tick_index for t in ticks_inst]
        y_prices = [t.price for t in ticks_inst]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=x_ticks,
                y=y_prices,
                mode="lines",
                name="Price",
                line=dict(color="#7dd3fc", width=2),
            )
        )

        decisions_inst = [
            d for d in recorder.decisions
            if d.instrument == inst or (inst in (d.instruments_affected or []))
        ]

        if decisions_inst:
            x_dec = []
            y_dec = []
            colors = []
            for d in decisions_inst:
                tick_idx = d.tick_index
                price = d.price
                if price is None:
                    matching = [t for t in ticks_inst if t.tick_index == tick_idx]
                    if matching:
                        price = matching[0].price
                    else:
                        nearby = [t for t in ticks_inst if t.tick_index <= tick_idx]
                        price = nearby[-1].price if nearby else y_prices[-1]
                x_dec.append(tick_idx)
                y_dec.append(price)
                colors.append(policy_colors.get(d.policy_kind, default_color))

            fig.add_trace(
                go.Scatter(
                    x=x_dec,
                    y=y_dec,
                    mode="markers+text",
                    name="Decisions",
                    marker=dict(size=12, color=colors, symbol="diamond", line=dict(width=2)),
                    text=[f" {d.policy_kind}" for d in decisions_inst],
                    textposition="top center",
                )
            )

        fig.update_layout(
            title=f"Price: {inst}",
            xaxis_title="Tick index",
            yaxis_title="Price",
            template="plotly_dark",
            paper_bgcolor="rgba(26,26,46,0)",
            plot_bgcolor="rgba(22,33,62,0.5)",
            font=dict(color="#eaeaea"),
            margin=dict(t=50, b=50, l=50, r=50),
            height=350,
        )

        include_js = "cdn" if idx == 0 else False
        frag = fig.to_html(full_html=False, include_plotlyjs=include_js)
        charts_html.append(f'<div class="chart-container">{frag}</div>')

    return "\n".join(charts_html)


def _build_dfid_tree_html(recorder: SimulationRecorder) -> str:
    """Build DFID hierarchy tree."""
    lines = []
    seen = set()
    for pos in recorder.positions:
        if pos.parent_dfid and pos.parent_dfid not in seen:
            seen.add(pos.parent_dfid)
            lines.append(f"<tr><td><code>{_escape(pos.parent_dfid[:12])}...</code></td><td>News (NEWS_QUALIFIED)</td></tr>")
        lines.append(
            f"<tr><td><code>{_escape(pos.position_id)}</code></td>"
            f"<td>Instrument manager for {_escape(pos.instrument)}"
            f" (parent: {_escape((pos.parent_dfid or '—')[:12])}...)</td></tr>"
        )
    if not lines:
        return "<p><em>No hierarchical DFID links (no positions spawned from news).</em></p>"
    return f"""
    <table class="data-table">
        <tr><th>DFID / Agent</th><th>Description</th></tr>
        {"".join(lines)}
    </table>"""


def _build_decisions_table_html(recorder: SimulationRecorder) -> str:
    """Build decisions table with details."""
    if not recorder.decisions:
        return "<p><em>No decisions recorded.</em></p>"

    rows = []
    for i, d in enumerate(recorder.decisions):
        dim_class = "ok" if d.dim_result == "ACCEPT" else "reject"
        rows.append(
            f"""
            <tr>
                <td>{d.tick_index}</td>
                <td><code>{_escape(d.dfid[:12])}...</code></td>
                <td>{_escape(d.agent_id)}</td>
                <td><span class="badge policy">{_escape(d.policy_kind)}</span></td>
                <td><span class="badge {dim_class}">{_escape(d.dim_result)}</span></td>
                <td>{_escape(d.instrument or "—")}</td>
                <td>
                    <details>
                        <summary>Details</summary>
                        <p><strong>Justification:</strong> {_escape(d.justification or "—")}</p>
                        <p><strong>Explain:</strong> {_escape((d.explain_narrative or "—")[:200])}</p>
                        <p><strong>DIM:</strong> {_escape(d.dim_reason)}</p>
                    </details>
                </td>
            </tr>"""
        )
    return f"""
    <table class="data-table">
        <tr><th>Tick</th><th>DFID</th><th>Agent</th><th>Policy</th><th>DIM</th><th>Instrument</th><th>Details</th></tr>
        {"".join(rows)}
    </table>"""


def _build_position_lifecycle_html(recorder: SimulationRecorder) -> str:
    """Build position lifecycle section."""
    if not recorder.positions:
        return "<p><em>No positions opened.</em></p>"

    blocks = []
    for pos in recorder.positions:
        events_html = f"""
            <p><strong>Opened:</strong> tick {pos.entry_tick}, price {pos.entry_price:.2f}</p>
            <p><strong>Trigger:</strong> {_escape(pos.news_headline or "OPEN_POSITION")}</p>
            <p><strong>Parent DFID:</strong> <code>{_escape((pos.parent_dfid or "—")[:16])}...</code></p>
        """
        if pos.lifecycle_events:
            events_html += "<p><strong>Lifecycle:</strong></p><ul>"
            for ev in pos.lifecycle_events:
                events_html += f"<li>Tick {ev['tick_index']}: {ev['policy_kind']} @ {ev['price']:.2f}"
                if ev.get("justification"):
                    events_html += f" — {_escape(ev['justification'][:80])}..."
                events_html += "</li>"
            events_html += "</ul>"
        else:
            events_html += "<p><em>No lifecycle events recorded.</em></p>"

        blocks.append(
            f"""
            <div class="position-block">
                <h4>{_escape(pos.position_id)} — {_escape(pos.instrument)}</h4>
                {events_html}
            </div>"""
        )
    return "\n".join(blocks)


def generate_html_report(
    recorder: SimulationRecorder,
    output_path: Path,
    simulation_ticks: int = 0,
    news_count: int = 0,
    elapsed_seconds: float = 0.0,
) -> None:
    """
    Generate complete HTML audit report for finance trading simulation.

    Args:
        recorder: SimulationRecorder with ticks, decisions, positions
        output_path: Where to save the HTML file
        simulation_ticks: Total ticks run
        news_count: Total news events
        elapsed_seconds: Wall-clock duration
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    chart_html = _build_chart_html(recorder)
    dfid_html = _build_dfid_tree_html(recorder)
    decisions_html = _build_decisions_table_html(recorder)
    lifecycle_html = _build_position_lifecycle_html(recorder)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Finance Trading — Simulation Report</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --surface: #16213e;
            --accent: #0f3460;
            --text: #eaeaea;
            --ok: #4ade80;
            --reject: #f87171;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
        }}
        h1 {{ color: #7dd3fc; margin-bottom: 0.5rem; }}
        h2 {{ color: #a5b4fc; font-size: 1.1rem; margin-top: 1.5rem; }}
        .meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 2rem; }}
        .summary-box {{
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 2rem;
        }}
        .chart-container {{
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }}
        details {{ margin: 0.5rem 0; }}
        summary {{ cursor: pointer; padding: 0.3rem 0; }}
        .section-content {{ padding: 0.5rem 0 1rem 1rem; }}
        .data-table {{
            border-collapse: collapse;
            width: 100%;
        }}
        .data-table th, .data-table td {{
            border: 1px solid var(--accent);
            padding: 0.5rem 0.75rem;
            text-align: left;
        }}
        .data-table th {{ width: 180px; color: #94a3b8; }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
        }}
        .badge.ok {{ background: var(--ok); color: #052e16; }}
        .badge.reject {{ background: var(--reject); color: #450a0a; }}
        .badge.policy {{ background: var(--accent); color: var(--text); }}
        code {{ background: var(--accent); padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.9em; }}
        .position-block {{
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        h4 {{ color: #94a3b8; font-size: 0.95rem; margin: 1rem 0 0.5rem 0; }}
    </style>
</head>
<body>
    <h1>Finance Trading — Simulation Report</h1>
    <p class="meta">Generated: {now} | Hierarchical DFID (EOAM)</p>

    <div class="summary-box">
        <h2>Summary</h2>
        <p><strong>Ticks:</strong> {simulation_ticks}</p>
        <p><strong>News events:</strong> {news_count}</p>
        <p><strong>Elapsed:</strong> {elapsed_seconds:.1f}s</p>
        <p><strong>Decisions:</strong> {len(recorder.decisions)}</p>
        <p><strong>Positions:</strong> {len(recorder.positions)}</p>
    </div>

    {_section("1. Price charts with decision points", chart_html, expanded=True)}

    {_section("2. DFID hierarchy tree", dfid_html)}

    {_section("3. Decision details", decisions_html)}

    {_section("4. Position lifecycle", lifecycle_html, expanded=True)}

    <p class="meta" style="margin-top: 2rem;">
        Hierarchical DFID: News agent (parent) spawns Instrument Manager (child).
        Full decision lifecycle and reasoning trace preserved for audit.
    </p>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
