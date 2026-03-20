"""
HTML report generator for the email pipeline (`generate_email_report`).

Per-email: rendered fixture, timeline, agent blocks when present, outcome.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from roa_underwriter_agent import DecisionCycleReport

try:
    from .pipeline import EmailCaseResult
except ImportError:
    from pipeline import EmailCaseResult


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


def _policy_proposal_dir_block(prop: Any) -> str:
    """Full PolicyProposal as JSON + DIR note (hash subset vs observability fields)."""
    pretty = json.dumps(
        prop.model_dump(), indent=2, sort_keys=True, default=str,
    )
    note = (
        '<p class="meta dir-proposal-note"><strong>DIR / PCI:</strong> '
        "<code>PolicyProposal</code> is the agent output serialized into the PCI "
        "<code>intent_payload</code> (JSON). Fields <code>total_insured_value</code>, "
        "<code>premium</code>, and <code>industry</code> are the binding subset "
        "used to compute <code>Evidence_Hash</code>; <code>justification</code> "
        "and <code>confidence</code> carry textual reasoning and self-assessed "
        "certainty for audit and UI (DIR-minified &sect;3.9: confidence is not "
        "authority) and are omitted from the hash input in this sample.</p>"
    )
    return (
        note
        + f'<pre class="policy-proposal-json"><code>{_escape(pretty)}</code></pre>'
    )


def _section(title: str, content: str, expanded: bool = True) -> str:
    open_attr = "" if expanded else ' open=""'
    return f"""
    <details{open_attr}>
        <summary><strong>{_escape(title)}</strong></summary>
        <div class="section-content">{content}</div>
    </details>"""


def _normalize_email_markdown(md_source: str) -> str:
    """Make fixture text friendlier for Markdown parsers (HR, spacing)."""
    # Long ASCII underlines (common in email fixtures) -> thematic break
    text = re.sub(r"(?m)^[ \t]*-{10,}[ \t]*$", "\n\n---\n\n", md_source)
    return text.strip() + ("\n" if text and not text.endswith("\n") else "")


def _inline_md_to_html(s: str) -> str:
    """Bold **x** and `code` for fallback renderer."""
    s = html_escape(s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _parse_pipe_table_row(line: str) -> List[str]:
    parts = [p.strip() for p in line.strip().split("|")]
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def _is_table_separator_row(line: str) -> bool:
    cells = _parse_pipe_table_row(line)
    if not cells:
        return False
    return all(re.match(r"^[\s:-]+$", c) for c in cells)


def _fallback_md_tables_and_paragraphs(md_source: str) -> str:
    """
    Render pipe tables, HR, and paragraphs when PyPI markdown is unavailable
    or raises. Good enough for London Market email fixtures.
    """
    lines = md_source.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        if re.match(r"^[-*]{3,}\s*$", stripped):
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("|") and stripped.count("|") >= 2:
            table_rows: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row_line = lines[i]
                if _is_table_separator_row(row_line):
                    i += 1
                    continue
                table_rows.append(_parse_pipe_table_row(row_line))
                i += 1
            if table_rows:
                out.append('<table class="md-fallback-table">')
                for ri, row in enumerate(table_rows):
                    tag = "th" if ri == 0 else "td"
                    out.append("<tr>")
                    for cell in row:
                        inner = _inline_md_to_html(cell)
                        out.append(f"<{tag}>{inner}</{tag}>")
                    out.append("</tr>")
                out.append("</table>")
            continue
        para_lines: List[str] = []
        while i < len(lines) and lines[i].strip():
            if lines[i].strip().startswith("|"):
                break
            if re.match(r"^[-*]{3,}\s*$", lines[i].strip()):
                break
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            text = " ".join(para_lines)
            out.append(f"<p>{_inline_md_to_html(text)}</p>")
        else:
            i += 1
        continue
    return "\n".join(out)


def _email_fixture_to_html(md_source: str) -> str:
    """
    Render markdown email fixture to HTML for the audit report.

    Tries PyPI ``markdown`` with table + fenced code extensions; on failure,
    missing package, or pipe tables not converted to HTML, uses a built-in
    fallback (pipe tables, **bold**, HR).
    """
    if not md_source.strip():
        return '<p class="meta">(empty source)</p>'
    normalized = _normalize_email_markdown(md_source)
    has_pipe_table = bool(re.search(r"(?m)^\s*\|[^\n]+\|", normalized))
    fragment: Optional[str] = None
    import_error = False
    try:
        import markdown

        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "nl2br"],
            extension_configs={
                "tables": {},
            },
        )
        fragment = md.convert(normalized)
    except ImportError:
        import_error = True
        fragment = None
    except Exception:
        fragment = None

    use_fallback = (
        fragment is None
        or not fragment.strip()
        or (has_pipe_table and "<table" not in fragment.lower())
    )
    if use_fallback:
        fragment = _fallback_md_tables_and_paragraphs(normalized)
        notice = ""
        if import_error:
            notice = (
                '<p class="meta md-fallback-notice">Package <code>markdown</code> not '
                "found; using built-in table renderer. Install: "
                '<code>pip install markdown</code> or '
                '<code>pip install -e &quot;.[samples]&quot;</code>.</p>'
            )
        return f'<div class="email-md-body">{notice}{fragment}</div>'
    return f'<div class="email-md-body">{fragment}</div>'


def _kernel_gate_timeline_detail(case: EmailCaseResult) -> str:
    """Human-readable kernel message from the step that blocked or escalated."""
    for s in reversed(case.timeline):
        if s.get("step") in ("GATE_REJECTED", "GATE_AUTHORITY_ESCALATED"):
            return (s.get("detail") or "").strip()
    return ""


def _dim_abort_timeline_detail(case: EmailCaseResult) -> str:
    for s in reversed(case.timeline):
        if s.get("step") == "FLOW_ABORTED":
            return (s.get("detail") or "").strip()
    return ""


def _clause_explanation(reason_code: str, case: EmailCaseResult) -> str:
    """Short mapping: which contract / config rule fired."""
    explanations: Dict[str, str] = {
        "AUTHORITY_CEILING": (
            "<strong>Delegated authority (<code>max_tiv</code>)</strong> — The "
            "underwriter agent’s responsibility contract caps bindable Total Insured Value. "
            "After extraction, <code>requested_tiv_usd</code> exceeded that cap, "
            "so the kernel escalated without issuing a policy."
        ),
        "PROHIBITED_TERRITORY": (
            "<strong>Prohibited geography (<code>email_processing.prohibited_territories</code>)"
            "</strong> — Kernel rule: agent-extracted territory text must not contain "
            "listed jurisdictions. A match blocks binding regardless of narrative in "
            "the raw email."
        ),
        "CONTRACT_VIOLATION": (
            "<strong>Multiple kernel rules</strong> — Both prohibited-territory and "
            "<code>max_tiv</code> checks failed on extracted facts."
        ),
        "PROMPT_INJECTION": (
            "<strong>Optional pre-LLM keyword gate</strong> — "
            "<code>email_processing.injection_patterns</code> matched the raw email "
            "body before any agent call."
        ),
        "EXTRACTION_FAILED": (
            "<strong>Structured extraction</strong> — The agent did not return valid "
            "<code>BROKER_REQUESTED_TIV_USD</code> and "
            "<code>STATED_TERRITORIES</code> lines, so the pipeline could not apply "
            "kernel numeric / geography checks."
        ),
        "POLICY_BOUND": (
            "<strong>Full path succeeded</strong> — Post-extraction gates passed, "
            "ROA cycle produced a PCI, DIM verified, ledger committed, mock bind ran."
        ),
    }
    if reason_code in explanations:
        return explanations[reason_code]
    if case.final_status == "BOUND":
        return explanations["POLICY_BOUND"]
    return (
        f"<strong>Outcome <code>{_escape(reason_code)}</code></strong> — See DIM "
        "result and timeline for the exact verifier message."
    )


def _decision_rationale_html(
    case: EmailCaseResult,
    contract: Dict[str, Any],
    email_processing: Dict[str, Any],
) -> str:
    max_lim = float(contract.get("max_tiv") or 0)
    prohibited_ind = contract.get("prohibited_industries") or []
    prohibited_ter = email_processing.get("prohibited_territories") or []
    inj = email_processing.get("injection_patterns") or []

    ext_lim = case.extracted_broker_tiv_usd
    ext_ter = getattr(case, "stated_territories_extracted", None)
    req_from_agent_ctx = None
    if case.report is not None:
        req_from_agent_ctx = case.report.context.requested_tiv_usd

    lim_display = "— (not extracted)"
    if ext_lim is not None:
        lim_display = f"{ext_lim:,.0f} USD TiV (from submission-facts extraction)"
    elif req_from_agent_ctx is not None:
        lim_display = f"{req_from_agent_ctx:,.0f} USD TiV (in agent context)"

    terr_display = "— (not extracted)"
    if ext_ter:
        terr_display = _escape(ext_ter[:1500]) + ("…" if len(ext_ter) > 1500 else "")

    contract_rows = f"""
    <tr><th>max_tiv (bindable TiV ceiling)</th><td>{_format_money(max_lim)}</td></tr>
    <tr><th>prohibited_industries</th><td>{_escape(", ".join(map(str, prohibited_ind)) or "—")}</td></tr>
    <tr><th>prohibited_territories (substring list)</th><td>{_escape(", ".join(map(str, prohibited_ter)) or "—")}</td></tr>
    <tr><th>injection_patterns (pre-LLM, optional)</th><td>{_escape(str(len(inj)) + " pattern(s)" if inj else "none (disabled)")}</td></tr>
    """

    facts_rows = f"""
    <tr><th>Extracted broker-requested TiV</th><td>{_escape(lim_display)}</td></tr>
    <tr><th>Extracted stated territories</th><td>{terr_display}</td></tr>
    """

    kernel_msg = _kernel_gate_timeline_detail(case)
    dim_abort = _dim_abort_timeline_detail(case)
    clause = _clause_explanation(case.reason_code, case)

    callouts = ""
    if kernel_msg:
        callouts += (
            f'<div class="kernel-message-callout"><strong>Kernel message</strong> '
            f"<p>{_escape(kernel_msg)}</p></div>"
        )
    if dim_abort and dim_abort != kernel_msg:
        callouts += (
            f'<div class="dim-abort-callout"><strong>DIM / verifier stop</strong> '
            f"<p>{_escape(dim_abort)}</p></div>"
        )

    return f"""
    <div class="decision-rationale">
        <h3 class="rationale-title">Decision rationale</h3>
        <p class="rationale-lead"><strong>Which rule applied:</strong> {clause}</p>
        {callouts}
        <div class="rationale-columns">
            <div class="rationale-col">
                <h4>Agent contract &amp; kernel config</h4>
                <p class="rationale-hint">Permissions and hard limits the runtime enforces.</p>
                <table class="data-table rationale-table">
                    {contract_rows}
                </table>
            </div>
            <div class="rationale-col">
                <h4>Facts used (after extraction)</h4>
                <p class="rationale-hint">What the agent read from the email for gates / ROA.</p>
                <table class="data-table rationale-table">
                    {facts_rows}
                </table>
            </div>
        </div>
    </div>"""


def _timeline_html(steps: List[Dict[str, Any]]) -> str:
    rows = ""
    for s in steps:
        rows += (
            f"<tr><td><code>{_escape(s.get('at', ''))}</code></td>"
            f"<td><strong>{_escape(str(s.get('step', '')))}</strong></td>"
            f"<td>{_escape(str(s.get('state', '')))}</td>"
            f"<td>{_escape(str(s.get('detail', '')))}</td></tr>"
        )
    return f"""
    <table class="data-table timeline">
        <tr><th>Time (UTC)</th><th>Step</th><th>State</th><th>Detail</th></tr>
        {rows}
    </table>"""


def _render_email_case(
    case: EmailCaseResult,
    contract: Dict[str, Any],
    email_processing: Dict[str, Any],
) -> str:
    st = case.final_status
    if st == "BOUND":
        badge_class, headline = "ok", "POLICY BOUND"
    elif st == "ESCALATED":
        badge_class, headline = "escalated", "ESCALATED (human review)"
    else:
        badge_class, headline = "reject", "REJECTED"

    policy_line = (
        f"<p><strong>Mock policy reference:</strong> <code>{_escape(case.policy_ref or '—')}</code></p>"
        if case.policy_ref
        else "<p><strong>Mock policy reference:</strong> — (not issued)</p>"
    )
    dim_line = f"<p><strong>DIM result:</strong> {_escape(case.dim_result or '— (not reached)')}</p>"

    rationale_html = _decision_rationale_html(case, contract, email_processing)

    agent_blocks = ""
    if case.report is not None:
        r = case.report
        ctx = r.context
        explain = r.explain_result
        prop = r.policy_proposal
        input_html = f"""
        <table class="data-table">
            <tr><th>business_type</th><td>{_escape(ctx.business_type)}</td></tr>
            <tr><th>revenue</th><td>{_format_money(ctx.revenue)}</td></tr>
            <tr><th>industry</th><td>{_escape(ctx.industry)}</td></tr>
            <tr><th>requested_tiv_usd</th><td>{_escape(str(ctx.requested_tiv_usd or '—'))}</td></tr>
            <tr><th>source_file</th><td>{_escape(ctx.source_file or '—')}</td></tr>
        </table>"""
        explain_html = f"""
        <p><em>Narrative:</em> {_escape(explain.get('narrative', ''))}</p>
        <p><strong>Signals:</strong> {_escape(', '.join(explain.get('signals', [])))}</p>"""
        just = (prop.justification or "").strip()
        policy_html = f"""
        <table class="data-table">
            <tr><th>total_insured_value (TiV)</th><td>{_format_money(prop.total_insured_value)}</td></tr>
            <tr><th>premium</th><td>{_format_money(prop.premium)}</td></tr>
            <tr><th>industry</th><td>{_escape(prop.industry)}</td></tr>
            <tr><th>confidence</th><td>{_escape(str(prop.confidence))}</td></tr>
            <tr><th>justification</th><td>{_escape(just[:1200])}{'…' if len(just) > 1200 else ''}</td></tr>
        </table>
        <p><em>Evidence hash (prefix):</em> <code>{_escape(r.evidence_hash[:16])}…</code></p>
        <h4 style="margin-top:1rem;color:#94a3b8;font-size:0.95rem;">PolicyProposal JSON (PCI intent_payload)</h4>
        {_policy_proposal_dir_block(prop)}"""
        agent_blocks = (
            _section("Agent: input context", input_html)
            + _section("Agent: Explain", explain_html)
            + _section("Agent: Policy + PCI", policy_html)
        )
    else:
        if getattr(case, "extracted_broker_tiv_usd", None) is not None:
            lim = case.extracted_broker_tiv_usd
            terr = getattr(case, "stated_territories_extracted", None) or ""
            terr_html = (
                f"<p><strong>Stated territories</strong> (from extraction): "
                f"{_escape(terr[:2000])}{'…' if len(terr) > 2000 else ''}</p>"
                if terr
                else ""
            )
            agent_blocks = _section(
                "Agent: submission facts extraction only",
                f"<p>Broker-requested TiV extracted from email (LLM): "
                f"<strong>{_escape(f'{lim:,.0f}')} USD</strong>.</p>"
                f"{terr_html}"
                "<p><strong>Why no Explain / Policy / PCI here:</strong> In this sample, "
                "the full ROA cycle runs only after post-extraction kernel gates pass "
                "(territory list and <code>max_tiv</code>). This flow stopped earlier, "
                "so there is no <code>PolicyProposal</code> or PCI yet—only structured "
                "facts for the kernel. That matches DIR: the agent’s formal proposal exists "
                "only once the runtime allows the decision path to continue to User Space "
                "ROA and then DIM.</p>",
            )
        else:
            agent_blocks = _section(
                "Agent: (not run)",
                "<p>Kernel gate stopped the flow before any agent LLM step.</p>",
            )

    timeline = _timeline_html(case.timeline)

    md_body = case.mail_body_markdown or ""
    email_source_html = _email_fixture_to_html(md_body)

    return f"""
    <div class="scenario-block">
        <h2>{_escape(case.mail_subject)}</h2>
        <p class="meta">Source: <code>{_escape(case.source_file)}</code> · DFID: <code>{_escape(case.dfid)}</code></p>
        <p><span class="badge {badge_class}">{headline}</span></p>
        <p class="reason-line"><strong>Reason code:</strong> {_escape(case.reason_code)} · <strong>Lifecycle:</strong> {_escape(case.lifecycle_state)}</p>
        {rationale_html}
        {dim_line}
        {policy_line}
        {_section("Source email (rendered from markdown)", email_source_html, expanded=True)}
        {_section("Processing timeline", timeline, expanded=True)}
        {agent_blocks}
    </div>"""


def generate_email_report(
    email_results: List[EmailCaseResult],
    contract: Dict[str, Any],
    ledger_count: int,
    audit_db_path: str,
    output_path: Path,
    email_processing: Optional[Dict[str, Any]] = None,
) -> None:
    """HTML report for email-driven underwriting pipeline."""
    ep = email_processing or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    blocks = "".join(_render_email_case(c, contract, ep) for c in email_results)
    bound_n = sum(1 for c in email_results if c.final_status == "BOUND")
    esc_n = sum(1 for c in email_results if c.final_status == "ESCALATED")
    rej_n = sum(1 for c in email_results if c.final_status == "REJECTED")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Digital Underwriter — Email Audit Report</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --surface: #16213e;
            --accent: #0f3460;
            --text: #eaeaea;
            --ok: #4ade80;
            --reject: #f87171;
            --esc: #fbbf24;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        .email-source-markdown {{
            white-space: pre-wrap;
            word-break: break-word;
            font-family: "Cascadia Code", Consolas, "Segoe UI Mono", ui-monospace, monospace;
            font-size: 0.82rem;
            line-height: 1.5;
            padding: 1rem 1.1rem;
            margin: 0;
            background: #0d1117;
            color: #e6edf3;
            border: 1px solid var(--accent);
            border-radius: 6px;
            overflow-x: auto;
            max-height: min(70vh, 48rem);
            overflow-y: auto;
        }}
        .email-md-body {{
            font-size: 0.92rem;
            line-height: 1.55;
            color: #e6edf3;
            background: #0d1117;
            border: 1px solid var(--accent);
            border-radius: 6px;
            padding: 1rem 1.25rem;
            overflow-x: auto;
            max-height: min(70vh, 48rem);
            overflow-y: auto;
        }}
        .email-md-body h1, .email-md-body h2, .email-md-body h3, .email-md-body h4 {{
            color: #a5b4fc;
            margin: 0.85rem 0 0.4rem;
            font-weight: 600;
            line-height: 1.3;
        }}
        .email-md-body h1 {{ font-size: 1.15rem; }}
        .email-md-body h2 {{ font-size: 1.05rem; }}
        .email-md-body h3, .email-md-body h4 {{ font-size: 0.98rem; }}
        .email-md-body p {{ margin: 0.5rem 0; }}
        .email-md-body p:first-child {{ margin-top: 0; }}
        .email-md-body p:last-child {{ margin-bottom: 0; }}
        .email-md-body strong {{ color: #f0f6fc; font-weight: 600; }}
        .email-md-body em {{ color: #c9d1d9; }}
        .email-md-body hr {{
            border: none;
            border-top: 1px solid #30363d;
            margin: 1rem 0;
        }}
        .email-md-body table {{
            border-collapse: collapse;
            width: 100%;
            margin: 0.75rem 0;
            font-size: 0.84rem;
        }}
        .email-md-body th,
        .email-md-body td {{
            border: 1px solid #30363d;
            padding: 0.4rem 0.55rem;
            vertical-align: top;
            text-align: left;
        }}
        .email-md-body th {{
            background: #161b22;
            color: #8b949e;
            font-weight: 600;
        }}
        .email-md-body tr:nth-child(even) td {{ background: rgba(22, 27, 34, 0.55); }}
        .email-md-body code {{
            background: #21262d;
            color: #79c0ff;
            padding: 0.12rem 0.35rem;
            border-radius: 4px;
            font-size: 0.88em;
        }}
        .email-md-body pre {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 0.75rem 1rem;
            overflow-x: auto;
            font-size: 0.82rem;
            line-height: 1.45;
        }}
        .email-md-body pre code {{
            background: transparent;
            color: #e6edf3;
            padding: 0;
        }}
        .email-md-body ul, .email-md-body ol {{
            margin: 0.5rem 0;
            padding-left: 1.35rem;
        }}
        .email-md-body li {{ margin: 0.25rem 0; }}
        .email-md-body blockquote {{
            margin: 0.75rem 0;
            padding-left: 1rem;
            border-left: 3px solid #388bfd;
            color: #8b949e;
        }}
        .email-md-body .md-fallback-table {{
            border-collapse: collapse;
            width: 100%;
            margin: 0.75rem 0;
            font-size: 0.84rem;
        }}
        .email-md-body .md-fallback-table th,
        .email-md-body .md-fallback-table td {{
            border: 1px solid #30363d;
            padding: 0.4rem 0.55rem;
            vertical-align: top;
            text-align: left;
        }}
        .email-md-body .md-fallback-table tr:first-child th,
        .email-md-body .md-fallback-table tr:first-child td {{
            background: #161b22;
            color: #8b949e;
            font-weight: 600;
        }}
        .md-fallback-notice {{
            background: #1f2a3d;
            border: 1px solid #388bfd;
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            margin-bottom: 0.75rem;
        }}
        .dir-proposal-note {{ line-height: 1.55; margin: 0.5rem 0 0.75rem; }}
        .policy-proposal-json {{
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 0.75rem 1rem;
            overflow-x: auto;
            font-size: 0.78rem;
            line-height: 1.45;
            margin: 0.5rem 0 0;
        }}
        .policy-proposal-json code {{
            background: transparent;
            padding: 0;
            white-space: pre;
            display: block;
        }}
        .decision-rationale {{
            background: linear-gradient(180deg, #1a2744 0%, #16213e 100%);
            border: 1px solid #3b82f6;
            border-radius: 10px;
            padding: 1.1rem 1.25rem 1.25rem;
            margin: 1rem 0 1.25rem;
            box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.15);
        }}
        .rationale-title {{
            color: #93c5fd;
            font-size: 1.05rem;
            margin: 0 0 0.5rem 0;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}
        .rationale-lead {{
            margin: 0 0 0.85rem 0;
            line-height: 1.55;
            color: #e2e8f0;
        }}
        .rationale-lead strong {{ color: #fbbf24; }}
        .kernel-message-callout, .dim-abort-callout {{
            background: #0d1117;
            border-left: 4px solid #fbbf24;
            padding: 0.65rem 0.9rem;
            margin: 0.65rem 0;
            border-radius: 0 6px 6px 0;
        }}
        .dim-abort-callout {{ border-left-color: #f87171; }}
        .kernel-message-callout p, .dim-abort-callout p {{
            margin: 0.35rem 0 0 0;
            color: #f1f5f9;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .kernel-message-callout strong, .dim-abort-callout strong {{
            color: #fde68a;
        }}
        .rationale-columns {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.1rem;
            margin-top: 0.75rem;
        }}
        @media (max-width: 900px) {{
            .rationale-columns {{ grid-template-columns: 1fr; }}
        }}
        .rationale-col h4 {{
            color: #a5b4fc;
            margin: 0 0 0.25rem 0;
            font-size: 0.95rem;
        }}
        .rationale-hint {{
            font-size: 0.82rem;
            color: #94a3b8;
            margin: 0 0 0.5rem 0;
        }}
        .rationale-table th {{ width: 42%; }}
        .reason-line {{ margin-bottom: 0.35rem; }}
        h1 {{ color: #7dd3fc; margin-bottom: 0.5rem; }}
        h2 {{ color: #a5b4fc; font-size: 1.05rem; margin-top: 0.5rem; }}
        .meta {{ color: #94a3b8; font-size: 0.88rem; margin-bottom: 1rem; }}
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
            font-size: 0.9rem;
        }}
        .data-table th, .data-table td {{
            border: 1px solid var(--accent);
            padding: 0.45rem 0.65rem;
            text-align: left;
            vertical-align: top;
        }}
        .data-table th {{ width: 160px; color: #94a3b8; }}
        .timeline td:nth-child(1) {{ white-space: nowrap; font-size: 0.8rem; }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.55rem;
            border-radius: 4px;
            font-weight: 600;
        }}
        .badge.ok {{ background: var(--ok); color: #052e16; }}
        .badge.reject {{ background: var(--reject); color: #450a0a; }}
        .badge.escalated {{ background: var(--esc); color: #422006; }}
        .summary-box {{
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 2rem;
        }}
        code {{ background: var(--accent); padding: 0.1rem 0.35rem; border-radius: 3px; font-size: 0.85em; }}
    </style>
</head>
<body>
    <h1>Digital Underwriter — Email pipeline audit</h1>
    <p class="meta">Generated: {now} | Topology C (DL+PCI) + mock bind API | SQLite: {_escape(audit_db_path)}</p>

    <div class="summary-box">
        <h2>Summary</h2>
        <p><strong>Policy (version):</strong> {_escape(contract.get('version', '—'))}</p>
        <p><strong>Max TiV (contract):</strong> {_format_money(float(contract.get('max_tiv', 0)))}</p>
        <p><strong>Emails processed:</strong> {len(email_results)} · <strong>Bound:</strong> {bound_n} ·
        <strong>Escalated:</strong> {esc_n} · <strong>Rejected:</strong> {rej_n}</p>
        <p><strong>Ledger entries (verified):</strong> {ledger_count}</p>
    </div>

    {blocks}

    <p class="meta" style="margin-top: 2rem;">
        DFID-tagged events are append-only in the audit database. Only DIM-verified decisions are
        committed to the ledger; the mock bind API runs after a successful ledger append.
    </p>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
