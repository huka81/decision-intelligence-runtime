"""
HTML report generator for finance trading simulation.

Produces a complete audit report: price charts with decision points, DFID hierarchy,
decision details (LLM justification, DIM result), and full position lifecycle.

Generates report from database (persistent storage) instead of in-memory data.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from telemetry import (
        SimulationReportState,
        hydrate_report_state_from_audit,
    )
except ImportError:
    from .telemetry import (
        SimulationReportState,
        hydrate_report_state_from_audit,
    )

from dir_core.storage import StorageBundle

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


def _related_dfids(state: SimulationReportState) -> Set[str]:
    """DFIDs tied to this simulation (ticks, decisions, news, position parents)."""
    s: Set[str] = set()
    for t in state.ticks:
        if t.dfid:
            s.add(t.dfid)
    for d in state.decisions:
        if d.dfid:
            s.add(d.dfid)
    for n in state.news_events:
        df = n.get("dfid")
        if df:
            s.add(str(df))
    for p in state.positions:
        if p.parent_dfid:
            s.add(p.parent_dfid)
    return s


def _agent_ids_for_run(state: SimulationReportState) -> List[str]:
    """Agent IDs that participate in audit + spawned position agents."""
    ids: Set[str] = {d.agent_id for d in state.decisions if d.agent_id}
    for p in state.positions:
        if p.position_id:
            ids.add(f"position_{p.position_id}")
    return sorted(ids)


def _fetch_flow_transitions(bundle: StorageBundle, allow_dfids: Set[str]) -> List[Dict[str, Any]]:
    """Read flow_transitions for DFIDs in this run (memory / PostgreSQL / SQLite)."""
    if not allow_dfids:
        return []
    ls = bundle.lifecycle
    mem_fn = getattr(ls, "get_transitions", None)
    if callable(mem_fn):
        rows: List[Dict[str, Any]] = []
        raw_transitions: Any = mem_fn()
        for t in raw_transitions:
            if t.get("dfid") in allow_dfids:
                rows.append(dict(t))
        rows.sort(key=lambda x: str(x.get("created_at", "")))
        return rows
    conn = getattr(ls, "_conn", None)
    flat = list(allow_dfids)[:400]
    if conn is not None and flat:
        placeholders = ",".join(["%s"] * len(flat))
        sql = (
            "SELECT id, dfid, from_status, to_status, created_at::text "
            "FROM flow_transitions WHERE dfid IN (" + placeholders + ") ORDER BY id ASC"
        )
        with conn.cursor() as cur:
            cur.execute(sql, flat)
            raw = cur.fetchall()
        return [
            {
                "id": r[0],
                "dfid": r[1],
                "from_status": r[2] or "",
                "to_status": r[3],
                "created_at": str(r[4]) if r[4] is not None else "",
            }
            for r in raw
        ]
    db_path = getattr(ls, "db_path", None)
    if db_path and flat:
        placeholders = ",".join("?" * len(flat))
        sql = (
            "SELECT id, dfid, from_status, to_status, created_at "
            "FROM flow_transitions WHERE dfid IN (" + placeholders + ") ORDER BY id ASC"
        )
        with sqlite3.connect(db_path) as c:
            cur = c.execute(sql, flat)
            raw = cur.fetchall()
        return [
            {
                "id": r[0],
                "dfid": r[1],
                "from_status": r[2] or "",
                "to_status": r[3],
                "created_at": str(r[4]) if r[4] is not None else "",
            }
            for r in raw
        ]
    return []


def _gather_registry_rows(bundle: StorageBundle, agent_ids: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for aid in agent_ids:
        rec = bundle.agent_registry.get_agent(aid)
        if not rec:
            continue
        c = rec.get("contract") or {}
        mission = str(c.get("mission") or "")
        rows.append(
            {
                "agent_id": aid,
                "status": rec.get("status", ""),
                "priority": rec.get("priority", 0),
                "role": str(c.get("role", "")),
                "instruments": ", ".join(c.get("authorized_instruments") or []),
                "mission_excerpt": mission[:160] + ("…" if len(mission) > 160 else ""),
            }
        )
    return rows


def _gather_session_snapshots(
    bundle: StorageBundle,
    simulation_id: str,
    dfids: Set[str],
    *,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Context Store session rows tagged with this simulation_id."""
    out: List[Dict[str, Any]] = []
    for i, dfid in enumerate(sorted(dfids)):
        if i >= limit:
            break
        raw = bundle.context.get_session(dfid)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("simulation_id") != simulation_id:
            continue
        steps = data.get("roa_internal_steps") or []
        last = steps[-1] if steps else {}
        out.append(
            {
                "dfid": dfid,
                "roa_steps": len(steps),
                "last_policy": str(last.get("policy_action", "—")),
                "last_outcome": str(last.get("outcome", "—")),
            }
        )
    return out


def _gather_agent_state_snapshots(
    bundle: StorageBundle,
    simulation_id: str,
    agent_ids: List[str],
) -> List[Dict[str, Any]]:
    """Context Store per-agent state for this simulation."""
    out: List[Dict[str, Any]] = []
    for aid in agent_ids:
        raw = bundle.context.get_state(aid)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if data.get("simulation_id") != simulation_id:
            continue
        out.append(
            {
                "agent_id": aid,
                "last_dfid": str(data.get("last_dfid", "—")),
                "last_policy": str(data.get("last_policy_action", "—")),
                "last_outcome": str(data.get("last_outcome", "—")),
            }
        )
    return out


def _transition_business_note(from_s: str, to_s: str) -> str:
    """Short business reading of a lifecycle row (sample-specific conventions)."""
    if from_s == "POSITION_SPAWN" and to_s.startswith("position_"):
        return "News flow spawned a dedicated position agent (capital at risk)."
    if to_s == "RETIRED":
        return "Position agent removed from active mesh after close (registry RETIRED)."
    if from_s == "NEWS_QUALIFIED" or "NEWS" in from_s.upper():
        return "Orchestration linked to news-qualified decision flow."
    return "Kernel lifecycle transition (audit trail)."


def _build_repository_business_html(
    bundle: StorageBundle,
    simulation_id: str,
    state: SimulationReportState,
) -> str:
    """HTML: registry, lifecycle, context session/state — data from the same StorageBundle as the run."""
    dfids = _related_dfids(state) | {simulation_id}
    agent_ids = _agent_ids_for_run(state)
    registry_rows = _gather_registry_rows(bundle, agent_ids)
    transitions = _fetch_flow_transitions(bundle, dfids)
    sessions = _gather_session_snapshots(bundle, simulation_id, dfids)
    states = _gather_agent_state_snapshots(bundle, simulation_id, agent_ids)

    intro = """
    <p class="meta">
        This section binds the <strong>trading narrative</strong> to DIR kernel artefacts persisted alongside
        decision audit: <em>who</em> was authorised in the Agent Registry, <em>which flows</em> recorded lifecycle
        transitions (spawn / retire), and <em>what</em> the Context Store captured per DFID and per agent state
        (ROA Explain→Policy outcomes for compliance and post-trade review).
    </p>
    """

    if not registry_rows and not transitions and not sessions and not states:
        return intro + (
            "<p><em>No Agent Registry / Context / lifecycle rows for agents in this run "
            "(e.g. in-memory bundle cleared, or kernel persistence not used for this execution).</em></p>"
        )

    blocks: List[str] = [intro]

    if registry_rows:
        rows_html = "".join(
            f"""<tr>
            <td><code>{_escape(str(r["agent_id"]))}</code></td>
            <td>{_escape(str(r["status"]))}</td>
            <td>{r["priority"]}</td>
            <td>{_escape(r["role"])}</td>
            <td>{_escape(r["instruments"])}</td>
            <td>{_escape(r["mission_excerpt"])}</td>
        </tr>"""
            for r in registry_rows
        )
        blocks.append(
            f"""
        <h3>Agent Registry — authority &amp; mission (DIR §2.3)</h3>
        <p class="meta">Registered agents participating in this simulation snapshot (contract + runtime status).</p>
        <table class="data-table">
            <tr><th>Agent</th><th>Status</th><th>Priority</th><th>Role</th><th>Instruments</th><th>Mission (excerpt)</th></tr>
            {rows_html}
        </table>"""
        )

    if transitions:
        tr_html = "".join(
            f"""<tr>
            <td>{_escape(str(t.get("created_at", "")))}</td>
            <td><code>{_escape(str(t.get("dfid", "")))}</code></td>
            <td>{_escape(str(t.get("from_status", "")))}</td>
            <td>{_escape(str(t.get("to_status", "")))}</td>
            <td>{_escape(_transition_business_note(str(t.get("from_status", "")), str(t.get("to_status", ""))))}</td>
        </tr>"""
            for t in transitions
        )
        blocks.append(
            f"""
        <h3>Flow lifecycle — orchestration (DIR §4.3)</h3>
        <p class="meta">Append-only transitions for DFIDs tied to this run (spawn of position agents, retire on close).</p>
        <table class="data-table">
            <tr><th>Time</th><th>Flow / DFID</th><th>From</th><th>To</th><th>Business note</th></tr>
            {tr_html}
        </table>"""
        )

    if sessions:
        s_html = "".join(
            f"""<tr>
            <td><code>{_escape(s["dfid"])}</code></td>
            <td>{s["roa_steps"]}</td>
            <td>{_escape(s["last_policy"])}</td>
            <td>{_escape(s["last_outcome"])}</td>
        </tr>"""
            for s in sessions
        )
        blocks.append(
            f"""
        <h3>Context Store — session (per DFID)</h3>
        <p class="meta">ROA internal steps persisted for each market/news decision flow (Explain→Policy outcome count).</p>
        <table class="data-table">
            <tr><th>DFID</th><th>ROA steps</th><th>Last policy</th><th>Last outcome</th></tr>
            {s_html}
        </table>"""
        )

    if states:
        st_html = "".join(
            f"""<tr>
            <td><code>{_escape(st["agent_id"])}</code></td>
            <td><code>{_escape(st["last_dfid"])}</code></td>
            <td>{_escape(st["last_policy"])}</td>
            <td>{_escape(st["last_outcome"])}</td>
        </tr>"""
            for st in states
        )
        blocks.append(
            f"""
        <h3>Context Store — agent state (authoritative slice)</h3>
        <p class="meta">Latest kernel-written state per agent for this simulation (ties agents to last DFID and policy outcome).</p>
        <table class="data-table">
            <tr><th>Agent</th><th>Last DFID</th><th>Last policy</th><th>Last outcome</th></tr>
            {st_html}
        </table>"""
        )

    return "\n".join(blocks)


def _build_chart_html(state: SimulationReportState) -> str:
    """Build Plotly charts for each instrument: price vs tick with decision points and rich tooltips."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return "<p><em>Chart requires plotly. Install: pip install plotly</em></p>"

    instruments = list({t.instrument for t in state.ticks if t.instrument})
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
        ticks_inst = [t for t in state.ticks if t.instrument == inst]
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
            d for d in state.decisions
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
            d for d in state.decisions
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
                    p for p in state.positions 
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
        positions_inst = [p for p in state.positions if p.instrument == inst]
        
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
                
                if pos.close_tick is not None and pos.close_price is not None:
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


def _build_dfid_tree_html(state: SimulationReportState) -> str:
    """Build DFID hierarchy tree."""
    lines = []
    seen = set()
    for pos in state.positions:
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


def _build_decisions_table_html(state: SimulationReportState) -> str:
    """Build decisions table with details."""
    if not state.decisions:
        return "<p><em>No decisions recorded.</em></p>"

    rows = []
    for i, d in enumerate(state.decisions):
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


def _build_position_lifecycle_html(state: SimulationReportState) -> str:
    """Build position lifecycle section with detailed audit trail."""
    if not state.positions:
        return "<p><em>No positions opened.</em></p>"

    blocks = []
    for pos in state.positions:
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
    bundle: StorageBundle,
    output_path: Path,
    simulation_ticks: int = 0,
    news_count: int = 0,
    elapsed_seconds: float = 0.0,
) -> None:
    """
    Generate complete HTML audit report for finance trading simulation from canonical database.
    """
    events = bundle.decision_audit.all_events_chronological()
    state = hydrate_report_state_from_audit(events, simulation_id)
    audit_event_count = sum(
        1
        for e in events
        if (e.get("details") or {}).get("simulation_id") == simulation_id
    )
    repository_html = _build_repository_business_html(bundle, simulation_id, state)

    # Generate report from loaded data
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    chart_html = _build_chart_html(state)
    dfid_html = _build_dfid_tree_html(state)
    decisions_html = _build_decisions_table_html(state)
    lifecycle_html = _build_position_lifecycle_html(state)

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
        <p><strong>Decisions:</strong> {len(state.decisions)}</p>
        <p><strong>Positions:</strong> {len(state.positions)}</p>
        <p><strong>Audit events (this simulation_id):</strong> {audit_event_count}</p>
    </div>

    {_section("🏛 Operating model & persisted kernel (DIR)", repository_html)}

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
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/simulation_data.db"),
        help="SQLite database path (only when config.yaml is missing or database.provider is sqlite)",
    )
    parser.add_argument("--output-path", type=Path, default=None, help="Where to save the HTML report")
    args = parser.parse_args()

    sample_dir = Path(__file__).resolve().parent
    config_path = sample_dir / "config.yaml"
    cli_db_path = args.db_path if args.db_path.is_absolute() else sample_dir / args.db_path

    from shared.config import load_yaml_config
    from shared.bootstrap import (
        normalize_database_provider,
        open_storage_bundle,
        resolve_sqlite_db_path_relative_to_config,
    )

    if config_path.exists():
        config = load_yaml_config(config_path)
        db_cfg = resolve_sqlite_db_path_relative_to_config(
            config.get("database") or {}, str(config_path)
        )
        db_provider = normalize_database_provider(db_cfg.get("provider", "memory"))
        if db_provider == "sqlite":
            sqlite_path = Path(db_cfg.get("db_path", "data/simulation_data.db"))
            if not sqlite_path.exists():
                print(f"SQLite database not found: {sqlite_path}")
                print("Run a simulation first to create the database.")
                exit(1)
        bundle = open_storage_bundle(db_cfg)
    else:
        if not cli_db_path.exists():
            print(f"Database not found: {cli_db_path}")
            print("Run a simulation first or add config.yaml with database settings.")
            exit(1)
        from dir_core.storage import sqlite_storage

        bundle = sqlite_storage(str(cli_db_path))
        
    events = bundle.decision_audit.all_events_chronological()
    
    # If no simulation ID provided, try to get the most recent one
    simulation_id = args.simulation_id
    sim_summary = {}
    if not simulation_id:
        for r in reversed(events):
            if r.get("event") == "SIMULATION_START":
                simulation_id = r.get("details", {}).get("simulation_id")
                sim_summary = r.get("details", {})
                break
        if not simulation_id:
            print("No simulations found in database.")
            exit(1)
        print(f"Using most recent simulation: {simulation_id}")
    
    # Determine output path
    if args.output_path:
        output_path = args.output_path
    else:
        sample_dir = Path(__file__).resolve().parent
        results_dir = sample_dir / "results"
        results_dir.mkdir(exist_ok=True)
        output_path = results_dir / f"report_{simulation_id}.html"
    
    generate_html_report(
        simulation_id=simulation_id,
        bundle=bundle,
        output_path=output_path,
        simulation_ticks=sim_summary.get("simulation_ticks", 0),
        news_count=sim_summary.get("total_news_events", 0),
        elapsed_seconds=sim_summary.get("elapsed_seconds", 0.0),
    )
    
    print(f"Report generated: {output_path}")
    print(f"\nOpening report in browser...")
    try:
        import webbrowser
        webbrowser.open(str(output_path.resolve()))
    except Exception as e:
        print(f"Could not open browser: {e}")
        print(f"Please open manually: {output_path}")
    