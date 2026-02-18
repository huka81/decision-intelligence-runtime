"""
HTML report generator for Digital Underwriter processing.

Produces a complete audit report: input data, agent processing, policy applied,
DIR verification, and final outcome (bound/rejected with reason).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from roa_underwriter_agent import DecisionCycleReport


def _escape(s: str) -> str:
    """Escape HTML special chars."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_money(v: float) -> str:
    return f"${v:,.0f}"


def _section(title: str, content: str, expanded: bool = True) -> str:
    open_attr = "" if expanded else ' open=""'
    return f"""
    <details{open_attr}>
        <summary><strong>{_escape(title)}</strong></summary>
        <div class="section-content">{content}</div>
    </details>"""


def _render_scenario(
    scenario_name: str,
    report: DecisionCycleReport,
    dim_result: str,
    contract: Dict[str, Any],
) -> str:
    """Render one scenario block."""
    ctx = report.context
    explain = report.explain_result
    prop = report.policy_proposal

    # 1. Input data (what the agent received)
    input_html = f"""
    <table class="data-table">
        <tr><th>business_type</th><td>{_escape(ctx.business_type)}</td></tr>
        <tr><th>revenue</th><td>{_format_money(ctx.revenue)}</td></tr>
        <tr><th>industry</th><td>{_escape(ctx.industry)}</td></tr>
    </table>"""

    # 2. Processing (Explain)
    explain_html = f"""
    <p><em>Narrative:</em> {_escape(explain.get("narrative", ""))}</p>
    <p><strong>Signals:</strong> {_escape(", ".join(explain.get("signals", [])))}</p>
    <p><strong>Risks:</strong> {_escape(", ".join(explain.get("risks", [])))}</p>
    <p><strong>Opportunities:</strong> {_escape(", ".join(explain.get("opportunities", [])))}</p>"""

    # 3. Applied policy (Policy) – includes audit fields (who, when created)
    policy_audit = f"""
    <h4>Policy audit metadata</h4>
    <table class="data-table">
        <tr><th>version</th><td>{_escape(contract.get("version", "—"))}</td></tr>
        <tr><th>created_by</th><td>{_escape(contract.get("created_by") or "—")}</td></tr>
        <tr><th>created_at</th><td>{_escape(contract.get("created_at") or "—")}</td></tr>
    </table>"""
    policy_proposal = f"""
    <h4>Proposal</h4>
    <table class="data-table">
        <tr><th>coverage_limit</th><td>{_format_money(prop.coverage_limit)}</td></tr>
        <tr><th>premium</th><td>{_format_money(prop.premium)}</td></tr>
        <tr><th>industry</th><td>{_escape(prop.industry)}</td></tr>
    </table>"""
    policy_html = policy_audit + policy_proposal

    # 4. Self-Check
    sc_status = "PASSED" if report.self_check_passed else "FAILED"
    sc_class = "ok" if report.self_check_passed else "reject"
    sc_reason = report.self_check_reason or "—"
    selfcheck_html = f"""
    <p><span class="badge {sc_class}">{sc_status}</span></p>
    <p><em>Reason:</em> {_escape(sc_reason)}</p>
    <p><em>Evidence hash forged:</em> {_escape("Yes" if report.forge_evidence_hash else "No")}</p>
    <p><em>DFID:</em> <code>{_escape(report.dfid[:8])}...</code></p>"""

    # 5. DIR (DIM)
    dim_class = "ok" if dim_result == "Policy Bound" else "reject"
    dim_msg = "approved and committed to Ledger" if dim_result == "Policy Bound" else "rejected"
    dim_html = f"""
    <p><span class="badge {dim_class}">{_escape(dim_result)}</span></p>
    <p>DIR (Decision Integrity Module) verified Evidence Hash and business rules.
    Policy was {dim_msg}.</p>"""

    # 6. Final outcome
    final_bound = dim_result == "Policy Bound"
    final_html = f"""
    <p class="outcome {'bound' if final_bound else 'rejected'}">
        <strong>Policy: {"BOUND" if final_bound else "REJECTED"}</strong>
    </p>
    <p><em>Reason:</em> {_escape(dim_result)}</p>"""

    blocks = [
        _section("1. Input data (what the agent received)", input_html),
        _section("2. Processing (Explain)", explain_html),
        _section("3. Applied policy (Policy)", policy_html),
        _section("4. Agent Self-Check", selfcheck_html),
        _section("5. DIR (DIM) verification", dim_html),
        _section("6. Final outcome", final_html, expanded=True),
    ]

    return f"""
    <div class="scenario-block">
        <h2>Scenario: {_escape(scenario_name)}</h2>
        {"".join(blocks)}
    </div>"""


def generate_html_report(
    scenarios: List[Dict[str, Any]],
    reports: List[DecisionCycleReport],
    results: List[str],
    contract: Dict[str, Any],
    ledger_count: int,
    output_path: Path,
) -> None:
    """
    Generate complete HTML audit report.

    Args:
        scenarios: List of scenario config dicts (name, etc.)
        reports: List of DecisionCycleReport from agent
        results: List of DIM results ("Policy Bound", "Evidence Invalid", etc.)
        contract: UnderwritingContract as dict
        ledger_count: Number of entries in Decision Ledger
        output_path: Where to save the HTML file
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    scenario_html = ""
    for sc, report, result in zip(scenarios, reports, results):
        scenario_html += _render_scenario(
            sc.get("name", "Scenario"),
            report,
            result,
            contract,
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Digital Underwriter - Audit Report</title>
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
        .scenario-block {{
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1.5rem;
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
        .outcome.bound {{ color: var(--ok); }}
        .outcome.rejected {{ color: var(--reject); }}
        code {{ background: var(--accent); padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.9em; }}
        .summary-box {{
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 2rem;
        }}
        h4 {{ color: #94a3b8; font-size: 0.95rem; margin: 1rem 0 0.5rem 0; }}
    </style>
</head>
<body>
    <h1>Digital Underwriter – Audit Report</h1>
    <p class="meta">Generated: {now} | Topology C (DL+PCI)</p>

    <div class="summary-box">
        <h2>Summary</h2>
        <p><strong>Policy (version):</strong> {_escape(contract.get("version", "—"))}</p>
        <p><strong>Created by:</strong> {_escape(contract.get("created_by") or "—")}</p>
        <p><strong>Created at:</strong> {_escape(contract.get("created_at") or "—")}</p>
        <p><strong>Ledger entries (verified):</strong> {ledger_count}</p>
        <p><strong>Scenarios:</strong> {len(scenarios)}</p>
    </div>

    {scenario_html}

    <p class="meta" style="margin-top: 2rem;">
        Day Two prevention: Only verified decisions are binding. Unverified agent
        outputs (hallucinations, forged proofs) never reach the Ledger.
    </p>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
