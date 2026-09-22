"""
HTML audit report for sample 33 (reconstructed from ``decision_audit_events`` only).

Source email bodies are read from ``emails/`` on disk using ``MAIL_INGESTED.file``.
No in-memory pipeline state is required.
"""

from __future__ import annotations

import argparse
import html
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
for _p in (_SRC, _SAMPLES, Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dir_core.storage import StorageBundle

from shared.bootstrap import materialize_storage_bundle
from shared.config import load_yaml_config

try:
    import markdown as _markdown
except ImportError:  # pragma: no cover - samples extra
    _markdown = None


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _new_report_path(sample_dir: Path, slug: str = "emails") -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return results_dir / f"report_{stamp}_{slug}.html"


def _events_for_latest_simulation_window(
    all_events: Sequence[Dict[str, Any]],
    simulation_id: str,
) -> List[Dict[str, Any]]:
    start_idx: Optional[int] = None
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
        out.append(e)
        if e.get("event") == "SIMULATION_END":
            d = e.get("details") or {}
            if d.get("simulation_id") == simulation_id:
                break
    return out


def _latest_simulation_id(all_events: Sequence[Dict[str, Any]]) -> Optional[str]:
    last: Optional[str] = None
    for e in all_events:
        if e.get("event") == "SIMULATION_START":
            d = e.get("details") or {}
            sid = d.get("simulation_id")
            if isinstance(sid, str):
                last = sid
    return last


def group_events_by_dfid(
    run_events: Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for e in run_events:
        event_name = e.get("event")
        if event_name in ("SIMULATION_START", "SIMULATION_END"):
            continue
        dfid = e.get("dfid")
        if not dfid:
            continue
        grouped.setdefault(str(dfid), []).append(e)
    return grouped


def terminal_outcome(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    for e in reversed(events):
        if e.get("event") == "FLOW_TERMINAL":
            return dict(e.get("details") or {})
    return {}


def _event_details(events: Sequence[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for e in events:
        if e.get("event") == name:
            return dict(e.get("details") or {})
    return {}


def _format_usd(amount: Any) -> str:
    try:
        return f"${float(amount):,.0f}"
    except (TypeError, ValueError):
        return str(amount)


def _hash_prefix(value: Any, length: int = 16) -> str:
    text = str(value or "")
    if len(text) <= length:
        return text
    return f"{text[:length]}…"


def _reason_codes_from_terminal(terminal: Dict[str, Any]) -> List[str]:
    codes = terminal.get("reason_codes") or []
    if codes:
        return [str(c) for c in codes]
    reason_code = str(terminal.get("reason_code", ""))
    if reason_code in ("", "—", "POLICY_BOUND"):
        return []
    return [c.strip() for c in reason_code.split(";") if c.strip()]


def _max_tiv_from_contract(contract: Dict[str, Any]) -> Optional[float]:
    for spec in (contract.get("authority") or {}).get("invariants") or []:
        if isinstance(spec, dict) and spec.get("id") == "INV_MAX_TIV":
            try:
                return float(spec["max"])
            except (TypeError, ValueError, KeyError):
                return None
    return None


def _contract_invariant_rows(contract: Dict[str, Any]) -> List[tuple[str, str]]:
    authority = contract.get("authority") or {}
    rows: List[tuple[str, str]] = []
    allowed = authority.get("allowed_policy_types") or []
    if allowed:
        rows.append(("allowed_policy_types", ", ".join(str(x) for x in allowed)))
    for spec in authority.get("invariants") or []:
        if not isinstance(spec, dict):
            continue
        inv_id = str(spec.get("id", "invariant"))
        reason = str(spec.get("reason_code", ""))
        if spec.get("type") == "set":
            denied = ", ".join(str(x) for x in (spec.get("denied") or []))
            match = str(spec.get("match", "exact"))
            field = str(spec.get("field", ""))
            rows.append(
                (
                    inv_id,
                    f"{field}: denied [{denied}] (match={match}) → {reason}",
                )
            )
        elif spec.get("type") == "range":
            field = str(spec.get("field", ""))
            maximum = spec.get("max")
            rows.append(
                (
                    inv_id,
                    f"{field} ≤ {_format_usd(maximum) if maximum is not None else maximum} → {reason}",
                )
            )
        else:
            rows.append((inv_id, reason or str(spec.get("type", ""))))
    return rows


def _rationale_lead(outcome: str, reason_codes: List[str]) -> str:
    if outcome == "BOUND":
        return (
            "<strong>Which rule applied:</strong> "
            "<strong>Full path succeeded</strong> — all contract invariants passed; "
            "ROA PCI verified, ledger committed, mock bind completed."
        )
    if outcome == "ESCALATED":
        return (
            "<strong>Which rule applied:</strong> "
            "<code>AUTHORITY_CEILING</code> — proposed TiV exceeds delegated ceiling; "
            "territory check passed."
        )
    if not reason_codes:
        return (
            "<strong>Which rule applied:</strong> "
            "DecisionFlow ended without a successful bind."
        )
    items = ", ".join(f"<code>{_esc(code)}</code>" for code in reason_codes)
    return (
        "<strong>Which rule applied:</strong> "
        f"DIM rejected the proposal. Failed invariant reason code(s): {items}."
    )


def _kernel_callout(events: Sequence[Dict[str, Any]], outcome: str) -> str:
    if outcome == "BOUND":
        return ""
    gate = _event_details(events, "GATE_REJECTED") or _event_details(
        events, "GATE_AUTHORITY_ESCALATED"
    )
    dim = _event_details(events, "DIM_RESULT")
    message = ""
    if gate:
        message = str(gate.get("message") or gate.get("code") or "")
    elif dim:
        message = str(dim.get("result") or "")
    if not message:
        return ""
    cls = "dim-abort-callout" if outcome == "REJECTED" else "kernel-message-callout"
    return (
        f'<div class="{cls}"><strong>Kernel message</strong>'
        f"<p>{_esc(message)}</p></div>"
    )


def _timeline_detail(event: str, details: Dict[str, Any]) -> str:
    if event == "FLOW_CREATED":
        return f"DecisionFlow opened for {_esc(details.get('file', 'email fixture'))}"
    if event == "MAIL_INGESTED":
        return (
            f"Read {_esc(details.get('file', ''))} "
            f"(sha256 {_hash_prefix(details.get('mail_body_sha256'), 12)})"
        )
    if event == "CONTEXT_COMPILED":
        return f"ClientApplication compiled — industry: {_esc(details.get('industry', '—'))}"
    if event == "POLICY_PROPOSAL_FAILED":
        return f"LLM / parser error: {_esc(details.get('error', ''))}"
    if event == "POLICY_PROPOSED":
        tiv = details.get("total_insured_value")
        territory = str(details.get("territory", ""))
        if len(territory) > 72:
            territory = territory[:72] + "…"
        return (
            f"TiV {_format_usd(tiv)}; territory: {_esc(territory)}"
        )
    if event == "PCI_EMITTED":
        tiv = details.get("total_insured_value")
        return (
            f"PCI emitted — TiV {_format_usd(tiv)}; "
            f"evidence_hash {_hash_prefix(details.get('evidence_hash'), 16)}"
        )
    if event == "DIM_RESULT":
        codes = details.get("reason_codes") or []
        if codes:
            return f"DIM: {_esc(details.get('result', ''))} [{', '.join(str(c) for c in codes)}]"
        return f"DIM: {_esc(details.get('result', ''))}"
    if event in ("GATE_REJECTED", "GATE_AUTHORITY_ESCALATED"):
        codes = details.get("reason_codes") or []
        code = details.get("code", "")
        if codes:
            return f"{_esc(event)} — {', '.join(str(c) for c in codes)}"
        return f"{_esc(event)} — {_esc(code)}"
    if event == "LEDGER_COMMITTED":
        return "PCI appended to Decision Ledger"
    if event == "BIND_REQUEST":
        return (
            f"Mock bind requested — TiV {_format_usd(details.get('total_insured_value'))} "
            f"(idempotency {_hash_prefix(details.get('idempotency_key_prefix'), 12)})"
        )
    if event == "BIND_SUCCEEDED":
        cached = details.get("cached")
        ref = details.get("policy_ref", "")
        suffix = " (cached replay)" if cached else ""
        return f"Policy bound — ref {_esc(ref)}{suffix}"
    if event == "FLOW_TERMINAL":
        outcome = details.get("outcome", "")
        reason = details.get("reason_code", "")
        return f"Terminal outcome {_esc(outcome)} — {_esc(reason)}"
    return "—"


def _timeline_rows(events: Sequence[Dict[str, Any]]) -> str:
    rows = ""
    for e in events:
        if e.get("event") in ("SIMULATION_START", "SIMULATION_END"):
            continue
        d = e.get("details") or {}
        detail = _timeline_detail(str(e.get("event", "")), d)
        rows += (
            f"<tr><td><code>{_esc(e.get('created_at', ''))}</code></td>"
            f"<td><strong>{_esc(e.get('event', ''))}</strong></td>"
            f"<td>{_esc(e.get('state', ''))}</td>"
            f"<td>{detail}</td></tr>"
        )
    return rows


def _render_markdown_email(sample_dir: Path, filename: str) -> str:
    path = sample_dir / "emails" / filename
    if not path.is_file():
        return f"<p><em>Fixture not found: {_esc(filename)}</em></p>"
    text = path.read_text(encoding="utf-8")
    if _markdown is not None:
        body = _markdown.markdown(text, extensions=["tables", "fenced_code"])
        return f'<div class="email-md-body">{body}</div>'
    return f'<pre class="email-source-markdown">{_esc(text)}</pre>'


def _table_rows(pairs: Sequence[tuple[str, str]]) -> str:
    return "".join(
        f"<tr><th>{_esc(label)}</th><td>{value}</td></tr>"
        for label, value in pairs
    )


def _proposal_facts_rows(proposal: Dict[str, Any]) -> List[tuple[str, str]]:
    if not proposal:
        return [("proposal", "— (not reached)")]
    territory = str(proposal.get("territory", "—"))
    justification = str(proposal.get("justification", ""))
    rows: List[tuple[str, str]] = [
        ("Proposed TiV", _format_usd(proposal.get("total_insured_value"))),
        ("Territory", _esc(territory)),
    ]
    if justification:
        rows.append(("Justification", _esc(justification)))
    return rows


def _render_flow_block(
    dfid: str,
    events: Sequence[Dict[str, Any]],
    sample_dir: Path,
    contract: Dict[str, Any],
) -> str:
    terminal = terminal_outcome(events)
    outcome = str(terminal.get("outcome", "UNKNOWN"))
    reason_code = str(terminal.get("reason_code", "—"))
    reason_codes = _reason_codes_from_terminal(terminal)
    lifecycle = str(terminal.get("lifecycle_state", "—"))
    policy_ref = terminal.get("policy_ref")

    if outcome == "BOUND":
        badge_cls, headline = "ok", "POLICY BOUND"
    elif outcome == "ESCALATED":
        badge_cls, headline = "escalated", "ESCALATED"
    else:
        badge_cls, headline = "reject", "REJECTED"

    mail = _event_details(events, "MAIL_INGESTED")
    subject = mail.get("subject", "—")
    source_file = mail.get("file", "—")
    body_sha = mail.get("mail_body_sha256", "—")

    proposal = _event_details(events, "POLICY_PROPOSED")
    pci = _event_details(events, "PCI_EMITTED")
    dim = _event_details(events, "DIM_RESULT")

    dim_result = dim.get("result", "— (not reached)") if dim else "— (not reached)"
    policy_line = (
        f'<p><strong>Mock policy reference:</strong> <code>{_esc(policy_ref)}</code></p>'
        if policy_ref
        else "<p><strong>Mock policy reference:</strong> — (not issued)</p>"
    )

    rationale = f"""
    <div class="decision-rationale">
        <h3 class="rationale-title">Decision rationale</h3>
        <p class="rationale-lead">{_rationale_lead(outcome, reason_codes)}</p>
        {_kernel_callout(events, outcome)}
        <div class="rationale-columns">
            <div class="rationale-col">
                <h4>Agent contract &amp; kernel config</h4>
                <p class="rationale-hint">Invariants enforced by DIM (<code>validate_proposal</code>).</p>
                <table class="data-table rationale-table">
                    {_table_rows(_contract_invariant_rows(contract))}
                </table>
            </div>
            <div class="rationale-col">
                <h4>Proposal facts (POLICY_PROPOSED)</h4>
                <p class="rationale-hint">Structured fields the agent put forward for validation.</p>
                <table class="data-table rationale-table">
                    {_table_rows(_proposal_facts_rows(proposal))}
                </table>
            </div>
        </div>
    </div>
    """

    pci_block = ""
    if pci or proposal:
        evidence = pci.get("evidence_hash", "") if pci else ""
        pci_block = f"""
        <table class="data-table">
            <tr><th>total_insured_value (TiV)</th><td>{_format_usd((pci or proposal).get('total_insured_value'))}</td></tr>
            <tr><th>territory</th><td>{_esc((pci or proposal).get('territory', '—'))}</td></tr>
            <tr><th>justification</th><td>{_esc((pci or proposal).get('justification', '—'))}</td></tr>
            <tr><th>evidence_hash (prefix)</th><td><code>{_esc(_hash_prefix(evidence, 16))}</code></td></tr>
        </table>
        <p class="meta dir-proposal-note"><strong>DIR / PCI:</strong> fields above are serialized in the PCI <code>intent_payload</code>; TiV and territory are hashed for <code>Evidence_Hash</code>.</p>
        """

    return f"""
    <div class="scenario-block">
        <h2>{_esc(subject)}</h2>
        <p class="meta">Source: <code>{_esc(source_file)}</code> · DFID: <code>{_esc(dfid)}</code></p>
        <p class="meta">mail_body_sha256: <code>{_esc(body_sha)}</code></p>
        <p><span class="badge {badge_cls}">{headline}</span></p>
        <p class="reason-line"><strong>Reason code:</strong> <code>{_esc(reason_code)}</code> · <strong>Lifecycle:</strong> {_esc(lifecycle)}</p>
        {rationale}
        <p><strong>DIM result:</strong> {_esc(dim_result)}</p>
        {policy_line}
        <details>
            <summary><strong>Source email (rendered from markdown)</strong></summary>
            <div class="section-content">{_render_markdown_email(sample_dir, str(source_file))}</div>
        </details>
        <details>
            <summary><strong>Processing timeline</strong></summary>
            <div class="section-content">
                <table class="data-table timeline">
                    <tr><th>Time (UTC)</th><th>Step</th><th>State</th><th>Detail</th></tr>
                    {_timeline_rows(events)}
                </table>
            </div>
        </details>
        <details>
            <summary><strong>Policy + PCI</strong></summary>
            <div class="section-content">{pci_block or '<p>— (not reached)</p>'}</div>
        </details>
    </div>
    """


def _report_styles() -> str:
    return """
        :root {
            --bg: #1a1a2e;
            --surface: #16213e;
            --accent: #0f3460;
            --text: #eaeaea;
            --ok: #4ade80;
            --reject: #f87171;
            --esc: #fbbf24;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        h1 { color: #7dd3fc; margin-bottom: 0.5rem; }
        h2 { color: #a5b4fc; font-size: 1.05rem; margin-top: 0.5rem; }
        .meta { color: #94a3b8; font-size: 0.88rem; margin-bottom: 0.5rem; }
        .summary-box {
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1rem 1.25rem;
            margin-bottom: 2rem;
        }
        .scenario-block {
            background: var(--surface);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .decision-rationale {
            background: linear-gradient(180deg, #1a2744 0%, #16213e 100%);
            border: 1px solid #3b82f6;
            border-radius: 10px;
            padding: 1.1rem 1.25rem 1.25rem;
            margin: 1rem 0 1.25rem;
        }
        .rationale-title { color: #93c5fd; font-size: 1.05rem; margin: 0 0 0.5rem 0; }
        .rationale-lead { margin: 0 0 0.85rem 0; line-height: 1.55; color: #e2e8f0; }
        .rationale-columns {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.1rem;
            margin-top: 0.75rem;
        }
        @media (max-width: 900px) { .rationale-columns { grid-template-columns: 1fr; } }
        .rationale-col h4 { color: #a5b4fc; margin: 0 0 0.25rem 0; font-size: 0.95rem; }
        .rationale-hint { font-size: 0.82rem; color: #94a3b8; margin: 0 0 0.5rem 0; }
        .rationale-table th { width: 42%; }
        .kernel-message-callout, .dim-abort-callout {
            background: #0d1117;
            border-left: 4px solid #fbbf24;
            padding: 0.65rem 0.9rem;
            margin: 0.65rem 0;
            border-radius: 0 6px 6px 0;
        }
        .dim-abort-callout { border-left-color: #f87171; }
        .kernel-message-callout p, .dim-abort-callout p { margin: 0.35rem 0 0 0; white-space: pre-wrap; }
        details { margin: 0.5rem 0; }
        summary { cursor: pointer; padding: 0.3rem 0; }
        .section-content { padding: 0.5rem 0 1rem 1rem; }
        .data-table { border-collapse: collapse; width: 100%; font-size: 0.9rem; margin: 0.5rem 0; }
        .data-table th, .data-table td {
            border: 1px solid var(--accent);
            padding: 0.45rem 0.65rem;
            text-align: left;
            vertical-align: top;
        }
        .data-table th { width: 160px; color: #94a3b8; }
        .timeline td:nth-child(1) { white-space: nowrap; font-size: 0.8rem; }
        .badge { display: inline-block; padding: 0.25rem 0.55rem; border-radius: 4px; font-weight: 600; }
        .badge.ok { background: var(--ok); color: #052e16; }
        .badge.reject { background: var(--reject); color: #450a0a; }
        .badge.escalated { background: var(--esc); color: #422006; }
        .reason-line { margin-bottom: 0.35rem; }
        code { background: var(--accent); padding: 0.1rem 0.35rem; border-radius: 3px; font-size: 0.85em; }
        .email-md-body, .email-source-markdown {
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
        }
        .email-md-body table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; font-size: 0.84rem; }
        .email-md-body th, .email-md-body td { border: 1px solid #30363d; padding: 0.4rem 0.55rem; }
        .email-md-body th { background: #161b22; color: #8b949e; }
        .email-md-body strong { color: #f0f6fc; }
        .email-source-markdown { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.82rem; }
        .dir-proposal-note { margin-top: 0.75rem; }
    """


def write_underwriting_html_report(
    bundle: StorageBundle,
    *,
    simulation_id: str,
    sample_dir: Path,
    config: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> Path:
    all_events = bundle.decision_audit.all_events_chronological()
    run_events = _events_for_latest_simulation_window(all_events, simulation_id)
    grouped = group_events_by_dfid(run_events)
    contract = dict((config.get("agents") or [{}])[0].get("contract") or {})
    metadata = contract.get("metadata") or {}

    outcomes = Counter(
        terminal_outcome(ev).get("outcome", "UNKNOWN") for ev in grouped.values()
    )
    bound_n = outcomes.get("BOUND", 0)
    esc_n = outcomes.get("ESCALATED", 0)
    rej_n = outcomes.get("REJECTED", 0)
    max_tiv = _max_tiv_from_contract(contract)

    blocks = "".join(
        _render_flow_block(dfid, evs, sample_dir, contract)
        for dfid, evs in grouped.items()
    )

    db_path = (config.get("database") or {}).get("db_path", "—")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    ledger_count = len(bundle.decision_ledger.all_entries_chronological())
    policy_version = metadata.get("version", "—")
    max_tiv_line = _format_usd(max_tiv) if max_tiv is not None else "—"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Digital Underwriter — Email Audit Report</title>
  <style>{_report_styles()}</style>
</head>
<body>
  <h1>Digital Underwriter — Email pipeline audit</h1>
  <p class="meta">Generated: {now} | Topology C (DL+PCI) + mock bind API | simulation_id: <code>{_esc(simulation_id)}</code></p>
  <p class="meta">Reconstructed from <code>decision_audit_events</code>. Email bodies from <code>emails/</code>. Audit DB: <code>{_esc(db_path)}</code></p>

  <div class="summary-box">
    <h2>Summary</h2>
    <p><strong>Policy (version):</strong> {_esc(policy_version)}</p>
    <p><strong>Max TiV (contract):</strong> {max_tiv_line}</p>
    <p><strong>Emails processed:</strong> {len(grouped)} ·
       <strong>Bound:</strong> {bound_n} ·
       <strong>Escalated:</strong> {esc_n} ·
       <strong>Rejected:</strong> {rej_n}</p>
    <p><strong>Ledger entries (verified):</strong> {ledger_count}</p>
  </div>
  {blocks}
</body>
</html>"""

    dest = output_path or _new_report_path(sample_dir)
    dest.write_text(html_doc, encoding="utf-8")
    return dest


def generate_email_report(
    bundle: StorageBundle,
    simulation_id: str,
    sample_dir: Path,
    config: Dict[str, Any],
    output_path: Path,
) -> Path:
    return write_underwriting_html_report(
        bundle,
        simulation_id=simulation_id,
        sample_dir=sample_dir,
        config=config,
        output_path=output_path,
    )


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Regenerate underwriting HTML report from decision_audit storage.",
    )
    parser.add_argument("--simulation-id", default="", help="Filter run (default: latest)")
    parser.add_argument("--output-path", default="", help="Write HTML to this path")
    parser.add_argument(
        "--config",
        default=str(sample_dir / "config.yaml"),
        help="Path to config.yaml",
    )
    args = parser.parse_args()
    cfg_path = Path(args.config).resolve()
    config = load_yaml_config(cfg_path)
    bundle = materialize_storage_bundle(config, config_path=str(cfg_path))
    all_ev = bundle.decision_audit.all_events_chronological()
    sim_id = args.simulation_id.strip() or _latest_simulation_id(all_ev) or ""
    if not sim_id:
        raise SystemExit("No SIMULATION_START found; run the sample first.")
    dest = Path(args.output_path).resolve() if args.output_path.strip() else None
    path = write_underwriting_html_report(
        bundle,
        simulation_id=sim_id,
        sample_dir=sample_dir,
        config=config,
        output_path=dest,
    )
    print(path)


if __name__ == "__main__":
    main()
