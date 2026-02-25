"""
HTML report generator for finance trading simulation.

Produces a complete audit report: price charts with decision points, DFID hierarchy,
decision details (LLM justification, DIM result), and full position lifecycle.

Generates report from database (persistent storage) instead of in-memory data.
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
from simulation_database import SimulationDatabase


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
    """Build Plotly charts for each instrument: price vs tick with decision points and rich tooltips."""
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
        
        # Prepare tick hover data
        tick_hover_data = [
            f"<b>Tick {t.tick_index}</b><br>"
            f"Price: ${t.price:.2f}<br>"
            f"Timestamp: {t.timestamp}<br>"
            f"Trend: {t.trend}<br>"
            f"Volatility: {t.volatility:.4f}<br>"
            f"DFID: {t.dfid}"
            for t in ticks_inst
        ]

        fig = go.Figure()
        
        # Price line with rich tooltips
        fig.add_trace(
            go.Scatter(
                x=x_ticks,
                y=y_prices,
                mode="lines+markers",
                name="Price",
                line=dict(color="#7dd3fc", width=2),
                marker=dict(size=4, color="#7dd3fc"),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=tick_hover_data,
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
            hover_texts = []
            
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
                
                # Build rich tooltip for decision
                justification = (d.justification or "—")[:150]
                if len(d.justification or "") > 150:
                    justification += "..."
                
                explain = (d.explain_narrative or "—")[:150]
                if len(d.explain_narrative or "") > 150:
                    explain += "..."
                
                hover_text = (
                    f"<b>{d.policy_kind}</b> @ Tick {tick_idx}<br>"
                    f"<b>Price:</b> ${price:.2f}<br>"
                    f"<b>Agent:</b> {d.agent_id}<br>"
                    f"<b>DIM:</b> {d.dim_result}<br>"
                    f"<b>DFID:</b> {d.dfid}<br>"
                    f"<br><b>Justification:</b><br>{justification}<br>"
                    f"<br><b>Explain:</b><br>{explain}<br>"
                    f"<br><b>DIM Reason:</b><br>{d.dim_reason[:100]}"
                )
                hover_texts.append(hover_text)

            # Decision markers with rich tooltips
            fig.add_trace(
                go.Scatter(
                    x=x_dec,
                    y=y_dec,
                    mode="markers",
                    name="Decisions",
                    marker=dict(
                        size=14, 
                        color=colors, 
                        symbol="diamond", 
                        line=dict(width=2, color="white")
                    ),
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=hover_texts,
                )
            )
        
        # Add NEWS_QUALIFIED events (news_scorer agent)
        news_qualified = [
            d for d in recorder.decisions
            if d.policy_kind == "NEWS_QUALIFIED" and (inst in (d.instruments_affected or []))
        ]
        
        if news_qualified:
            x_news = []
            y_news = []
            hover_news = []
            
            for d in news_qualified:
                tick_idx = d.tick_index
                # Get price at this tick
                matching = [t for t in ticks_inst if t.tick_index == tick_idx]
                if matching:
                    price = matching[0].price
                elif ticks_inst:
                    nearby = [t for t in ticks_inst if t.tick_index <= tick_idx]
                    price = nearby[-1].price if nearby else y_prices[-1]
                else:
                    continue
                
                x_news.append(tick_idx)
                # Offset news markers up by 3% to avoid overlap with position markers
                y_news.append(price * 1.03)
                
                # Find associated positions spawned from this news
                spawned_positions = [
                    p for p in recorder.positions 
                    if p.parent_dfid == d.dfid and p.instrument == inst
                ]
                pos_info = ""
                if spawned_positions:
                    pos_ids = ", ".join([p.position_id[:8] for p in spawned_positions])
                    pos_info = f"<br><b>Spawned Positions:</b> {pos_ids}..."
                
                justification = (d.justification or "—")[:150]
                if len(d.justification or "") > 150:
                    justification += "..."
                
                hover_text = (
                    f"<b>📰 NEWS QUALIFIED</b> @ Tick {tick_idx}<br>"
                    f"<b>Price:</b> ${price:.2f}<br>"
                    f"<b>Agent:</b> {d.agent_id}<br>"
                    f"<b>Instruments:</b> {', '.join(d.instruments_affected or [])}<br>"
                    f"<b>DFID:</b> {d.dfid}<br>{pos_info}<br>"
                    f"<br><b>Justification:</b><br>{justification}"
                )
                hover_news.append(hover_text)
            
            if x_news:
                fig.add_trace(
                    go.Scatter(
                        x=x_news,
                        y=y_news,
                        mode="markers",
                        name="News Qualified",
                        marker=dict(
                            size=18, 
                            color="#60a5fa",
                            symbol="star", 
                            line=dict(width=2, color="white")
                        ),
                        hovertemplate="%{customdata}<extra></extra>",
                        customdata=hover_news,
                    )
                )
        
        # Add OPEN_POSITION markers
        positions_inst = [p for p in recorder.positions if p.instrument == inst]
        
        if positions_inst:
            x_open = []
            y_open = []
            hover_open = []
            
            for pos in positions_inst:
                x_open.append(pos.entry_tick)
                # Offset position markers down by 3% to avoid overlap with news markers
                y_open.append(pos.entry_price * 0.97)
                
                hover_text = (
                    f"<b>📈 POSITION OPENED</b><br>"
                    f"<b>Position ID:</b> {pos.position_id}<br>"
                    f"<b>Tick:</b> {pos.entry_tick}<br>"
                    f"<b>Entry Price:</b> ${pos.entry_price:.2f}<br>"
                    f"<b>Exposure:</b> ${pos.initial_exposure:.2f}<br>"
                    f"<b>Quantity:</b> {pos.quantity:.6f}<br>"
                )
                
                if pos.news_headline:
                    headline = pos.news_headline[:100]
                    if len(pos.news_headline) > 100:
                        headline += "..."
                    hover_text += f"<br><b>News Trigger:</b><br>{headline}<br>"
                
                if pos.parent_dfid:
                    hover_text += f"<br><b>Parent DFID:</b> {pos.parent_dfid}"
                
                if pos.close_tick is not None:
                    pnl_usd = pos.quantity * (pos.close_price - pos.entry_price)
                    pnl_percent = ((pos.close_price - pos.entry_price) / pos.entry_price) * 100
                    pnl_sign = "+" if pnl_usd >= 0 else ""
                    hover_text += (
                        f"<br><br><b>Closed:</b> Tick {pos.close_tick} @ ${pos.close_price:.2f}<br>"
                        f"<b>P&L:</b> {pnl_sign}{pnl_percent:.2f}% ({pnl_sign}${pnl_usd:.2f})<br>"
                        f"<b>Reason:</b> {pos.close_reason}"
                    )
                else:
                    hover_text += "<br><br><b>Status:</b> OPEN"
                
                hover_open.append(hover_text)
            
            if x_open:
                fig.add_trace(
                    go.Scatter(
                        x=x_open,
                        y=y_open,
                        mode="markers",
                        name="Position Open",
                        marker=dict(
                            size=20, 
                            color="#10b981",
                            symbol="triangle-up", 
                            line=dict(width=3, color="white")
                        ),
                        hovertemplate="%{customdata}<extra></extra>",
                        customdata=hover_open,
                    )
                )

        fig.update_layout(
            title=dict(
                text=f"<b>{inst}</b> — Price Movement & Agent Decisions",
                font=dict(size=16, color="#7dd3fc")
            ),
            xaxis_title="Tick Index",
            yaxis_title="Price (USD)",
            template="plotly_dark",
            paper_bgcolor="rgba(26,26,46,0)",
            plot_bgcolor="rgba(22,33,62,0.5)",
            font=dict(color="#eaeaea", size=12),
            margin=dict(t=60, b=50, l=60, r=50),
            height=450,
            hovermode='closest',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
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
            lines.append(f"<tr><td><code>{_escape(pos.parent_dfid)}</code></td><td>News (NEWS_QUALIFIED)</td></tr>")
        lines.append(
            f"<tr><td><code>{_escape(pos.position_id)}</code></td>"
            f"<td>Instrument manager for {_escape(pos.instrument)}"
            f" (parent: {_escape(pos.parent_dfid or '—')})</td></tr>"
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
                <td><code>{_escape(d.dfid)}</code></td>
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
    """Build position lifecycle section with detailed audit trail."""
    if not recorder.positions:
        return "<p><em>No positions opened.</em></p>"

    blocks = []
    for pos in recorder.positions:
        # Determine status
        status_emoji = "✅" if pos.close_tick is not None else "⏳"
        status_text = "CLOSED" if pos.close_tick is not None else "OPEN"
        status_class = "closed" if pos.close_tick is not None else "open"
        
        # Calculate P&L if closed
        pnl_html = ""
        if pos.close_tick is not None and pos.close_price is not None:
            pnl_usd = pos.quantity * (pos.close_price - pos.entry_price)
            pnl_percent = ((pos.close_price - pos.entry_price) / pos.entry_price) * 100
            pnl_color = "profit" if pnl_usd >= 0 else "loss"
            pnl_sign = "+" if pnl_usd >= 0 else ""
            pnl_html = f"""
                <div class="pnl-box {pnl_color}">
                    <strong>P&L:</strong> {pnl_sign}{pnl_percent:.2f}% ({pnl_sign}${pnl_usd:.2f} USD)
                </div>
            """
        
        # Opening details
        opening_html = f"""
            <div class="lifecycle-section">
                <h5>📈 POSITION OPENED</h5>
                <div class="details-grid">
                    <div><strong>Tick:</strong> {pos.entry_tick}</div>
                    <div><strong>Price:</strong> ${pos.entry_price:.2f}</div>
                    <div><strong>Exposure:</strong> ${pos.initial_exposure:.2f}</div>
                    <div><strong>Quantity:</strong> {pos.quantity:.6f}</div>
                </div>
            </div>
        """
        
        # News trigger if available
        news_html = ""
        if pos.news_headline:
            news_html = f"""
                <div class="lifecycle-section news-section">
                    <h5>📰 NEWS TRIGGER</h5>
                    <p class="news-headline">"{_escape(pos.news_headline)}"</p>
                    <p class="news-meta"><strong>Parent DFID:</strong> <code>{_escape(pos.parent_dfid or "—")}</code></p>
                </div>
            """
        
        # Lifecycle events
        events_html = ""
        if pos.lifecycle_events:
            events_list = []
            for ev in pos.lifecycle_events:
                policy_class = ev['policy_kind'].lower().replace('_', '-')
                events_list.append(f"""
                    <div class="event-row policy-{policy_class}">
                        <span class="event-tick">Tick {ev['tick_index']}</span>
                        <span class="event-policy">{ev['policy_kind']}</span>
                        <span class="event-price">@ ${ev['price']:.2f}</span>
                        {f'<p class="event-just">{_escape(ev.get("justification", "")[:120])}...</p>' if ev.get("justification") else ''}
                    </div>
                """)
            events_html = f"""
                <div class="lifecycle-section">
                    <h5>📊 LIFECYCLE EVENTS</h5>
                    <div class="events-timeline">
                        {"".join(events_list)}
                    </div>
                </div>
            """
        
        # Closing details
        closing_html = ""
        if pos.close_tick is not None:
            closing_html = f"""
                <div class="lifecycle-section closing-section">
                    <h5>🏁 POSITION CLOSED</h5>
                    <div class="details-grid">
                        <div><strong>Tick:</strong> {pos.close_tick}</div>
                        <div><strong>Price:</strong> ${pos.close_price:.2f}</div>
                        <div><strong>Reason:</strong> {_escape(pos.close_reason or "—")}</div>
                    </div>
                    {pnl_html}
                </div>
            """
        else:
            closing_html = f"""
                <div class="lifecycle-section open-section">
                    <h5>⏳ POSITION STILL OPEN</h5>
                    <p>Decisions so far: {len(pos.lifecycle_events)}</p>
                </div>
            """
        
        # Combine into position block
        blocks.append(f"""
            <div class="position-card {status_class}">
                <div class="position-header">
                    <div class="position-title">
                        <span class="status-badge-{status_class}">{status_emoji} {status_text}</span>
                        <h4>{_escape(pos.position_id)}</h4>
                        <span class="instrument-badge">{_escape(pos.instrument)}</span>
                    </div>
                </div>
                {opening_html}
                {news_html}
                {events_html}
                {closing_html}
            </div>
        """)
    
    return "\n".join(blocks)


def generate_html_report(
    simulation_id: str,
    db_path: str | Path,
    output_path: Path,
    simulation_ticks: int = 0,
    news_count: int = 0,
    elapsed_seconds: float = 0.0,
) -> None:
    """
    Generate complete HTML audit report for finance trading simulation from database.

    Args:
        simulation_id: Simulation ID to load data for
        db_path: Path to simulation_data.db
        output_path: Where to save the HTML file
        simulation_ticks: Total ticks run
        news_count: Total news events
        elapsed_seconds: Wall-clock duration
    """
    # Load data from database
    db = SimulationDatabase(db_path)
    db.connect()
    
    try:
        # Load all data for this simulation
        ticks_data = db.load_ticks(simulation_id)
        decisions_data = db.load_decisions(simulation_id)
        positions_data = db.load_positions(simulation_id)
        news_events_data = db.load_news_events(simulation_id)
        
        # Create temporary recorder with loaded data
        recorder = SimulationRecorder()
        
        # Convert loaded data to recorder format
        for t in ticks_data:
            recorder.ticks.append(TickRecord(
                tick_index=t['tick_index'],
                instrument=t['instrument'],
                price=t['price'],
                timestamp=t['timestamp'],
                dfid=t['dfid'],
                trend=t.get('trend', 'neutral'),
                volatility=t.get('volatility', 0.0),
            ))
        
        for d in decisions_data:
            recorder.decisions.append(SimDecisionRecord(
                tick_index=d['tick_index'],
                dfid=d['dfid'],
                parent_dfid=d.get('parent_dfid'),
                agent_id=d['agent_id'],
                policy_kind=d['policy_kind'],
                justification=d.get('justification'),
                dim_result=d['dim_result'],
                dim_reason=d['dim_reason'],
                explain_narrative=d.get('explain_narrative'),
                explain_signals=d.get('explain_signals', []),
                explain_risks=d.get('explain_risks', []),
                explain_opportunities=d.get('explain_opportunities', []),
                instrument=d.get('instrument'),
                price=d.get('price'),
                event_type=d['event_type'],
                instruments_affected=d.get('instruments_affected', []),
            ))
        
        for p in positions_data:
            recorder.positions.append(PositionRecord(
                position_id=p['position_id'],
                instrument=p['instrument'],
                entry_tick=p['entry_tick'],
                entry_price=p['entry_price'],
                initial_exposure=p['initial_exposure'],
                current_exposure=p['current_exposure'],
                quantity=p['quantity'],
                parent_dfid=p.get('parent_dfid'),
                news_headline=p.get('news_headline'),
                lifecycle_events=p.get('lifecycle_events', []),
                close_tick=p.get('close_tick'),
                close_price=p.get('close_price'),
                close_reason=p.get('close_reason'),
            ))
        
        recorder.news_events = news_events_data
        
    finally:
        db.close()
    
    # Generate report from loaded data
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
            --bg: #0f0f1e;
            --bg-lighter: #1a1a2e;
            --surface: #16213e;
            --surface-hover: #1f2f4e;
            --accent: #0f3460;
            --accent-bright: #1e5a9e;
            --text: #eaeaea;
            --text-dim: #94a3b8;
            --ok: #4ade80;
            --reject: #f87171;
            --warning: #fbbf24;
            --info: #60a5fa;
            --border: #2a3f5f;
        }}
        
        * {{ box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, var(--bg-lighter) 100%);
            color: var(--text);
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        h1 {{ 
            color: #7dd3fc; 
            margin-bottom: 0.5rem;
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}
        
        h2 {{ 
            color: #a5b4fc; 
            font-size: 1.3rem; 
            margin-top: 2rem;
            margin-bottom: 1rem;
            font-weight: 600;
        }}
        
        h4 {{
            color: var(--text);
            font-size: 1rem;
            margin: 0;
            font-weight: 600;
        }}
        
        h5 {{
            color: var(--text-dim);
            font-size: 0.9rem;
            margin: 0 0 0.75rem 0;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .meta {{ 
            color: var(--text-dim); 
            font-size: 0.9rem; 
            margin-bottom: 2rem; 
        }}
        
        /* Summary Box */
        .summary-box {{
            background: linear-gradient(135deg, var(--surface) 0%, var(--accent) 100%);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        
        .summary-box h2 {{
            margin-top: 0;
            color: #7dd3fc;
        }}
        
        .summary-box p {{
            margin: 0.5rem 0;
            font-size: 1rem;
        }}
        
        /* Chart Container */
        .chart-container {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        
        /* Position Cards */
        .position-card {{
            background: var(--surface);
            border: 2px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .position-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.4);
        }}
        
        .position-card.closed {{
            border-color: var(--ok);
        }}
        
        .position-card.open {{
            border-color: var(--info);
        }}
        
        .position-header {{
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }}
        
        .position-title {{
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        
        .status-badge-closed,
        .status-badge-open {{
            padding: 0.4rem 0.8rem;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }}
        
        .status-badge-closed {{
            background: var(--ok);
            color: #052e16;
        }}
        
        .status-badge-open {{
            background: var(--info);
            color: #0c1e3a;
        }}
        
        .instrument-badge {{
            background: var(--accent-bright);
            color: var(--text);
            padding: 0.3rem 0.6rem;
            border-radius: 4px;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        
        /* Lifecycle Sections */
        .lifecycle-section {{
            background: var(--bg-lighter);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        
        .news-section {{
            background: linear-gradient(135deg, var(--bg-lighter) 0%, var(--accent) 100%);
            border-color: var(--info);
        }}
        
        .closing-section {{
            background: linear-gradient(135deg, var(--bg-lighter) 0%, rgba(74, 222, 128, 0.1) 100%);
            border-color: var(--ok);
        }}
        
        .open-section {{
            background: linear-gradient(135deg, var(--bg-lighter) 0%, rgba(96, 165, 250, 0.1) 100%);
            border-color: var(--info);
        }}
        
        .details-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 0.75rem;
            margin-top: 0.5rem;
        }}
        
        .details-grid div {{
            background: var(--surface);
            padding: 0.5rem;
            border-radius: 4px;
            border: 1px solid var(--border);
        }}
        
        .news-headline {{
            font-size: 1rem;
            font-style: italic;
            color: var(--info);
            margin: 0.5rem 0;
            padding: 0.5rem;
            background: var(--surface);
            border-left: 3px solid var(--info);
            border-radius: 4px;
        }}
        
        .news-meta {{
            font-size: 0.85rem;
            color: var(--text-dim);
            margin: 0.5rem 0;
        }}
        
        /* Events Timeline */
        .events-timeline {{
            margin-top: 0.75rem;
        }}
        
        .event-row {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem;
            margin-bottom: 0.5rem;
            background: var(--surface);
            border-left: 3px solid var(--text-dim);
            border-radius: 4px;
            transition: background 0.2s;
        }}
        
        .event-row:hover {{
            background: var(--surface-hover);
        }}
        
        .event-row.policy-hold {{
            border-left-color: var(--ok);
        }}
        
        .event-row.policy-reduce {{
            border-left-color: var(--warning);
        }}
        
        .event-row.policy-close,
        .event-row.policy-close-position {{
            border-left-color: var(--reject);
        }}
        
        .event-row.policy-open-position {{
            border-left-color: var(--info);
        }}
        
        .event-tick {{
            font-weight: 600;
            color: var(--text-dim);
            min-width: 60px;
        }}
        
        .event-policy {{
            background: var(--accent);
            color: var(--text);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85rem;
            min-width: 120px;
            text-align: center;
        }}
        
        .event-price {{
            color: var(--ok);
            font-weight: 600;
        }}
        
        .event-just {{
            width: 100%;
            margin: 0.5rem 0 0 0;
            padding: 0.5rem;
            background: var(--bg-lighter);
            border-radius: 4px;
            font-size: 0.85rem;
            color: var(--text-dim);
            border-left: 2px solid var(--accent);
        }}
        
        /* P&L Box */
        .pnl-box {{
            margin-top: 1rem;
            padding: 0.75rem;
            border-radius: 6px;
            font-size: 1.1rem;
            font-weight: 700;
            text-align: center;
        }}
        
        .pnl-box.profit {{
            background: var(--ok);
            color: #052e16;
        }}
        
        .pnl-box.loss {{
            background: var(--reject);
            color: #450a0a;
        }}
        
        /* Tables */
        details {{ 
            margin: 1rem 0;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.5rem;
        }}
        
        summary {{ 
            cursor: pointer; 
            padding: 0.75rem;
            font-weight: 600;
            color: var(--info);
            transition: color 0.2s;
        }}
        
        summary:hover {{
            color: #7dd3fc;
        }}
        
        .section-content {{ 
            padding: 1rem;
        }}
        
        .data-table {{
            border-collapse: collapse;
            width: 100%;
            background: var(--bg-lighter);
        }}
        
        .data-table th, .data-table td {{
            border: 1px solid var(--border);
            padding: 0.75rem;
            text-align: left;
        }}
        
        .data-table th {{ 
            background: var(--accent);
            color: var(--text);
            font-weight: 600;
        }}
        
        .data-table tr:hover {{
            background: var(--surface-hover);
        }}
        
        /* Badges */
        .badge {{
            display: inline-block;
            padding: 0.3rem 0.6rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85rem;
        }}
        
        .badge.ok {{ 
            background: var(--ok); 
            color: #052e16; 
        }}
        
        .badge.reject {{ 
            background: var(--reject); 
            color: #450a0a; 
        }}
        
        .badge.policy {{ 
            background: var(--accent-bright); 
            color: var(--text); 
        }}
        
        code {{ 
            background: var(--accent); 
            padding: 0.2rem 0.4rem; 
            border-radius: 3px; 
            font-size: 0.9em;
            font-family: 'Courier New', monospace;
        }}
        
        /* Responsive */
        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}
            
            .details-grid {{
                grid-template-columns: 1fr;
            }}
            
            .event-row {{
                flex-wrap: wrap;
            }}
        }}
    </style>
</head>
<body>
    <h1>📊 Finance Trading — Simulation Report</h1>
    <p class="meta">Generated: {now} | Hierarchical DFID (EOAM) | Simulation ID: {simulation_id}</p>

    <div class="summary-box">
        <h2>📋 Summary</h2>
        <p><strong>Ticks:</strong> {simulation_ticks}</p>
        <p><strong>News events:</strong> {news_count}</p>
        <p><strong>Elapsed:</strong> {elapsed_seconds:.1f}s</p>
        <p><strong>Decisions:</strong> {len(recorder.decisions)}</p>
        <p><strong>Positions:</strong> {len(recorder.positions)}</p>
    </div>

    <h2>📈 Price Charts with Decision Points</h2>
    <p class="meta">Hover over price line to see tick details. Hover over decision markers to see LLM justification and agent proposal.</p>
    {chart_html}

    {_section("🔗 DFID Hierarchy Tree", dfid_html)}

    {_section("📝 Decision Details", decisions_html)}

    <h2>💼 Position Lifecycle Reports</h2>
    {lifecycle_html}

    <p class="meta" style="margin-top: 2rem;">
        Hierarchical DFID: News agent (parent) spawns Instrument Manager (child).
        Full decision lifecycle and reasoning trace preserved for audit.
    </p>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Generate HTML report for finance trading simulation")
    parser.add_argument("--simulation-id", type=str, help="Simulation ID to load (uses most recent if not specified)")
    parser.add_argument("--db-path", type=Path, default=Path("data/simulation_data.db"), help="Path to simulation_data.db")
    parser.add_argument("--output-path", type=Path, default=None, help="Where to save the HTML report")
    args = parser.parse_args()

    # Resolve database path
    db_path = args.db_path if args.db_path.is_absolute() else Path(__file__).parent / args.db_path
    
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run a simulation first to create the database.")
        exit(1)
    
    db = SimulationDatabase(db_path)
    db.connect()
    
    # If no simulation ID provided, try to get the most recent one
    simulation_id = args.simulation_id
    if not simulation_id:
        try:
            result = db.conn.execute(
                "SELECT simulation_id FROM simulations ORDER BY run_timestamp DESC LIMIT 1"
            ).fetchone()
            if result:
                simulation_id = result[0]
                print(f"Using most recent simulation: {simulation_id}")
            else:
                print("No simulations found in database.")
                db.close()
                exit(1)
        except Exception as e:
            print(f"Error querying database: {e}")
            db.close()
            exit(1)
    
    sim_summary = db.get_simulation_summary(simulation_id)
    if not sim_summary:
        print(f"Simulation {simulation_id} not found in database.")
        db.close()
        exit(1)
    
    db.close()

    # Determine output path
    if args.output_path:
        output_path = args.output_path
    else:
        sample_dir = Path(__file__).resolve().parent
        results_dir = sample_dir / "results"
        results_dir.mkdir(exist_ok=True)
        output_path = results_dir / f"simulation_report_{simulation_id}.html"
    
    generate_html_report(
        simulation_id=simulation_id,
        db_path=db_path,
        output_path=output_path,
        simulation_ticks=sim_summary.get("simulation_ticks", 0),
        news_count=sim_summary.get("total_news_events", 0),
        elapsed_seconds=sim_summary.get("elapsed_seconds", 0.0),
    )
    
    print(f"✅ Report generated: {output_path}")
    print(f"\nOpening report in browser...")
    try:
        import webbrowser
        webbrowser.open(str(output_path.resolve()))
    except Exception as e:
        print(f"Could not open browser: {e}")
        print(f"Please open manually: {output_path}")
    