"""
HTML audit report for ``32_fraud_gate`` (Sample Development Guide §17).

Data source: ``bundle.decision_audit.all_events_chronological()`` plus registry,
context store, and read-only SQLite ``flow_transitions`` when applicable.

Charts (§17.4 Section 3) are intentionally omitted—this sample keeps the report tabular only.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))

_SAMPLE_DIR = Path(__file__).resolve().parent
if str(_SAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(_SAMPLE_DIR))

from dir_core import AgentRegistry, ContextStore
from dir_core.storage import StorageBundle

from shared.bootstrap import materialize_storage_bundle, normalize_database_provider
from shared.config import load_yaml_config

from schemas import ScenarioConfig, load_scenarios


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _new_report_path(sample_dir: Path, slug: str = "") -> Path:
    results_dir = sample_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    suffix = f"_{slug}" if slug else ""
    return results_dir / f"report_{stamp}{suffix}.html"


def _events_for_latest_simulation_window(
    all_events: Sequence[Dict[str, Any]],
    simulation_id: str,
) -> List[Dict[str, Any]]:
    """Events from the most recent SIMULATION_START for ``simulation_id`` through its SIMULATION_END.

    Avoids mixing multiple historical runs that reused the same ``run_id`` / ``simulation_id``.
    """
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


def _sqlite_db_path(config: Dict[str, Any]) -> Optional[str]:
    db = config.get("database") or {}
    if normalize_database_provider(db.get("provider", "memory")) != "sqlite":
        return None
    raw = db.get("db_path")
    return str(raw) if raw else None


def _read_flow_transitions_ro(db_path: str) -> List[Dict[str, Any]]:
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT dfid, from_status, to_status, created_at "
            "FROM flow_transitions ORDER BY id ASC"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _scenario_description_prose(config: Dict[str, Any]) -> str:
    jit = config.get("jit_validator") or {}
    fg = config.get("fraud_gate") or {}
    rules = fg.get("fallback_rules") or {}
    gmax = jit.get("global_max_limit", 50_000)
    block_amt = rules.get("block_amount_threshold", 5000)
    allow_max = rules.get("allow_amount_max", 1000)
    countries = rules.get("block_high_risk_countries", ["nigeria"])
    esc = None
    agents = config.get("agents") or []
    if agents:
        esc = (agents[0].get("contract") or {}).get("escalate_on_uncertainty")
    esc_s = f"{esc}" if esc is not None else "(see config)"
    return f"""
<p>This sample demonstrates a <strong>classic YAML-driven fraud gate</strong> with a full ROA cycle
(Explain → Policy → deterministic Self-Check → <code>PolicyProposal</code>), then DIM validation
with custom JIT rules including snapshot versus live risk projection and a deliberate TOCTOU drift
injection on one scenario row.</p>
<p>Thresholds wired from <code>config.yaml</code> for this report narrative:
<code>jit_validator.global_max_limit = {gmax}</code>,
<code>fraud_gate.fallback_rules.block_amount_threshold = {block_amt}</code>,
<code>allow_amount_max = {allow_max}</code>,
high-risk geography list <code>{_esc(countries)}</code>,
and contract <code>escalate_on_uncertainty = {esc_s}</code> (policies below this confidence never
become proposals).</p>
<p>Per-scenario amounts, DIM outcomes, and expected verdicts are summarized in Section 4—this sample
omits chart figures to keep the audit report minimal.</p>
"""


def _trace_table_row(
    idx: int,
    ev: Dict[str, Any],
    *,
    expected: str,
    executed: bool,
    match_exp: bool,
) -> str:
    d = ev.get("details") or {}
    dfid = str(ev.get("dfid", ""))
    dfid_short = (dfid[:8] + "…") if len(dfid) > 8 else dfid
    verdict = str(d.get("verdict", ""))
    vcls = "badge-ok" if verdict == "ACCEPT" else "badge-reject"
    mcls = "badge-ok" if match_exp else "badge-warn"
    narrative = str(d.get("explain_narrative", ""))
    justification = str(d.get("justification", ""))
    sc_pass = d.get("self_check_passed", True)
    return f"""
<tr>
  <td>{idx}</td>
  <td><code title="{_esc(dfid)}">{_esc(dfid_short)}</code></td>
  <td>{_esc(d.get("scenario_label", ""))}</td>
  <td>{_esc(d.get("tx_id", ""))}</td>
  <td>{_esc(d.get("amount", ""))}</td>
  <td>{_esc(d.get("geo_country", ""))}</td>
  <td><span class="{vcls}">{_esc(verdict)}</span></td>
  <td>{_esc("yes" if executed else "no")}</td>
  <td><span class="{mcls}">{"match" if match_exp else "mismatch"}</span> (expected {_esc(expected)})</td>
  <td>
    <details>
      <summary>Reasoning</summary>
      <div class="details-body">
        <p><strong>Justification:</strong> {_esc(justification)}</p>
        <p><strong>Explain narrative:</strong> {_esc(narrative)}</p>
        <p><strong>Policy action:</strong> {_esc(d.get("policy_proposed_action", d.get("policy_kind", "")))}</p>
        <p><strong>Self-check:</strong> {_esc("passed" if sc_pass else "failed")} —
          {_esc(d.get("self_check_reason", ""))}</p>
        <p><strong>DIM reason:</strong> {_esc(d.get("reason", ""))}</p>
      </div>
    </details>
  </td>
</tr>
"""


def _roa_block(ev: Dict[str, Any], *, executed: bool, execution_note: str) -> str:
    d = ev.get("details") or {}
    dfid = str(ev.get("dfid", ""))
    agent_id = str(d.get("agent_id", ""))
    role = str(d.get("contract_role", ""))
    scope = str(d.get("user_id", ""))
    verdict = str(d.get("verdict", ""))
    allowed = d.get("contract_allowed_policy_types") or []
    allowed_s = json.dumps(allowed, default=str)
    signals = d.get("explain_signals") or []
    risks = d.get("explain_risks") or []
    opps = d.get("explain_opportunities") or []
    narrative = str(d.get("explain_narrative", "")) or "(not recorded)"
    sc_pass = bool(d.get("self_check_passed", True))
    sc_reas = str(d.get("self_check_reason", ""))
    inner = f"""
<pre class="roa-pre">
DFID: {_esc(dfid)}
Agent: {_esc(agent_id)}  Role: {_esc(role)}  Scope (user): {_esc(scope)}

[EXPLAIN]
  Narrative:   {_esc(narrative)}
  Signals:     {_esc(signals)}
  Risks:       {_esc(risks)}
  Opportunities: {_esc(opps)}

[POLICY]
  Proposed action:  {_esc(d.get("policy_proposed_action", d.get("policy_kind", "")))}
  Confidence (policy stage): {_esc(d.get("policy_stage_confidence", d.get("confidence", "")))}
  Justification:    {_esc(d.get("justification", ""))}

[SELF-CHECK]
  Passed: {"yes" if sc_pass else "no"}
  Reason (if failed): {_esc(sc_reas)}

[DIM VALIDATION]
  Verdict:  {_esc(verdict)}
  Reason:   {_esc(d.get("reason", ""))}
  Contract: role={_esc(role)}  allowed_policy_types={_esc(allowed_s)}

[EXECUTION]
  Executed: {"yes" if executed else "no"}
  Side effect: {_esc(execution_note)}
</pre>
"""
    return f"""
<details open="">
  <summary><strong>ROA trace — {_esc(d.get("scenario_label", ""))}</strong></summary>
  <div class="section-content">{inner}</div>
</details>
"""


def _kernel_section(
    bundle: StorageBundle,
    config: Dict[str, Any],
    dfids: List[str],
    agent_id_fallback: str,
) -> str:
    registry = AgentRegistry(storage=bundle.agent_registry)
    store = ContextStore(storage=bundle.context)
    agents = registry.list_agents()
    if not agents:
        agents = [agent_id_fallback] if agent_id_fallback else []

    reg_rows = []
    for aid in agents:
        st = registry.get_agent_status(aid)
        status_s = st[0] if st else "(unknown)"
        susp = st[1] if st and st[1] else ""
        contract = registry.get_agent_contract(aid) or {}
        mission = str(contract.get("mission", ""))[:160]
        reg_rows.append(
            "<tr>"
            f"<td><code>{_esc(aid)}</code></td>"
            f"<td>{_esc(status_s)}</td>"
            f"<td>{_esc(susp)}</td>"
            f"<td>{registry.get_agent_priority(aid)}</td>"
            f"<td>{_esc(contract.get('role', ''))}</td>"
            f"<td>{_esc(contract.get('authorized_instruments', []))}</td>"
            f"<td>{_esc(mission)}</td>"
            "</tr>"
        )
    reg_html = (
        "<table class='data'><thead><tr>"
        "<th>agent_id</th><th>status</th><th>suspension</th><th>priority</th>"
        "<th>role</th><th>authorized_instruments</th><th>mission (excerpt)</th>"
        "</tr></thead><tbody>"
        + "".join(reg_rows)
        + "</tbody></table>"
    )

    db_path = _sqlite_db_path(config)
    if db_path and Path(db_path).is_file():
        try:
            transitions = _read_flow_transitions_ro(db_path)
        except OSError:
            transitions = []
    else:
        transitions = []

    if transitions:
        tr_rows = []
        for t in transitions[-200:]:
            tr_rows.append(
                "<tr>"
                f"<td>{_esc(t.get('created_at', ''))}</td>"
                f"<td><code>{_esc(t.get('dfid', ''))}</code></td>"
                f"<td>{_esc(t.get('from_status', ''))}</td>"
                f"<td>{_esc(t.get('to_status', ''))}</td>"
                "<td>Lifecycle transition recorded in canonical store.</td>"
                "</tr>"
            )
        flow_html = (
            "<table class='data'><thead><tr>"
            "<th>created_at</th><th>dfid</th><th>from_status</th><th>to_status</th>"
            "<th>note</th></tr></thead><tbody>"
            + "".join(tr_rows)
            + "</tbody></table>"
        )
    else:
        flow_html = (
            '<p class="muted">No rows in <code>flow_transitions</code> for this database '
            "(this sample does not call <code>bundle.lifecycle.record_transition</code>).</p>"
        )

    ctx_rows = []
    for dfid in dfids[:50]:
        sess = store.get_session(dfid)
        tx = (sess.get("transaction") or {}) if isinstance(sess, dict) else {}
        last_action = tx.get("amount", "")
        ctx_rows.append(
            "<tr>"
            f"<td><code>{_esc(dfid)}</code></td>"
            f"<td>{len(sess) if isinstance(sess, dict) else 0}</td>"
            f"<td>{_esc(sess.get('scenario_label', ''))}</td>"
            f"<td>{_esc(last_action)}</td>"
            "</tr>"
        )
    ctx_html = (
        "<table class='data'><thead><tr>"
        "<th>dfid</th><th>session keys</th><th>scenario_label</th><th>txn amount</th>"
        "</tr></thead><tbody>"
        + "".join(ctx_rows)
        + "</tbody></table>"
    )

    return f"""
<details>
  <summary><strong>Section 7 — DIR kernel artefacts</strong></summary>
  <div class="section-content">
    <h4>Agent registry</h4>
    {reg_html}
    <h4>Flow lifecycle transitions</h4>
    {flow_html}
    <h4>Context store sessions (decision flows in this run)</h4>
    {ctx_html}
  </div>
</details>
"""


def write_fraud_gate_html_report(
    bundle: StorageBundle,
    *,
    simulation_id: str,
    sample_dir: Path,
    config: Dict[str, Any],
    scenario_count: int,
    elapsed_sec: float,
    run_status: str,
    output_path: Optional[Path] = None,
) -> Path:
    all_ev = bundle.decision_audit.all_events_chronological()
    run_ev = _events_for_latest_simulation_window(all_ev, simulation_id)
    slug = f"{scenario_count}scenarios"
    out_path = output_path if output_path else _new_report_path(sample_dir, slug)
    if output_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    start_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    llm_backend = "unknown"
    sim_end_status = ""
    for e in run_ev:
        if e.get("event") == "SIMULATION_START":
            llm_backend = str((e.get("details") or {}).get("llm_backend") or llm_backend)
        if e.get("event") == "SIMULATION_END":
            sim_end_status = str((e.get("details") or {}).get("status", ""))

    counts = Counter(str(e.get("event", "")) for e in run_ev)
    decisions = [e for e in run_ev if e.get("event") == "AGENT_DECISION"]
    payments = {str(e.get("dfid")): e for e in run_ev if e.get("event") == "PAYMENT_GATEWAY_ALLOW"}

    scenarios_path = sample_dir / "scenarios.yaml"
    scenarios: List[ScenarioConfig] = (
        load_scenarios(scenarios_path) if scenarios_path.is_file() else []
    )
    expected_by_label = {s.label: s.expected for s in scenarios}

    trace_rows = []
    for i, e in enumerate(decisions, start=1):
        d = e.get("details") or {}
        dfid = str(e.get("dfid", ""))
        label = str(d.get("scenario_label", ""))
        exp = expected_by_label.get(label, "")
        executed = dfid in payments
        match_exp = str(d.get("verdict", "")).upper() == str(exp).upper() if exp else False
        trace_rows.append(_trace_table_row(i, e, expected=exp, executed=executed, match_exp=match_exp))

    roa_blocks = []
    for e in decisions:
        d = e.get("details") or {}
        dfid = str(e.get("dfid", ""))
        executed = dfid in payments
        pay = payments.get(dfid)
        if executed and pay:
            pd = pay.get("details") or {}
            note = (
                f"PAYMENT_GATEWAY_ALLOW tx_id={pd.get('tx_id')} amount={pd.get('amount')} "
                f"cached={pd.get('cached')}"
            )
        elif str(d.get("verdict", "")).upper() == "ACCEPT" and str(d.get("policy_kind", "")) != "ALLOW":
            note = "DIM ACCEPT but policy is not ALLOW — mock gateway logs only (no settlement)."
        else:
            note = "blocked — no settlement"
        roa_blocks.append(_roa_block(e, executed=executed, execution_note=note))

    registry = AgentRegistry(storage=bundle.agent_registry)
    reg_list = registry.list_agents()
    agent_fb = reg_list[0] if reg_list else ""
    if not agent_fb and decisions:
        agent_fb = str((decisions[0].get("details") or {}).get("agent_id", ""))

    kernel = _kernel_section(
        bundle,
        config,
        [str(e.get("dfid", "")) for e in decisions],
        agent_fb,
    )

    agents_cfg = config.get("agents") or []
    primary_agent = str(agents_cfg[0].get("agent_id", "fraud_guard_v1")) if agents_cfg else agent_fb

    summary_reg = []
    for aid in registry.list_agents() or ([primary_agent] if primary_agent else []):
        st = registry.get_agent_status(aid)
        summary_reg.append(
            f"<li><code>{_esc(aid)}</code> — {_esc(st[0] if st else '?')}"
            f"{(' — ' + _esc(str(st[1]))) if st and st[1] else ''}</li>"
        )
    reg_summary_ul = "<ul>" + "".join(summary_reg) + "</ul>" if summary_reg else "<p class='muted'>(none)</p>"

    css = """
:root {
  --bg: #0d1117;
  --fg: #e6edf3;
  --muted: #8b949e;
  --border: #30363d;
  --ok: #3fb950;
  --reject: #f85149;
  --warn: #d29922;
  --info: #58a6ff;
}
* { box-sizing: border-box; }
body {
  font-family: ui-sans-serif, system-ui, sans-serif;
  background: var(--bg);
  color: var(--fg);
  margin: 0;
  padding: 2rem;
}
.wrap { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 1.35rem; margin-top: 0; }
h2 { font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.35rem; }
h3 { font-size: 1rem; margin-top: 1.25rem; }
.meta { color: var(--muted); font-size: 0.9rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; margin: 1rem 0; }
.card { border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; background: #161b22; }
.badge-ok { color: var(--ok); font-weight: 600; }
.badge-reject { color: var(--reject); font-weight: 600; }
.badge-warn { color: var(--warn); font-weight: 600; }
table.data { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 0.75rem 0; }
table.data th, table.data td { border: 1px solid var(--border); padding: 0.45rem 0.5rem; text-align: left; vertical-align: top; }
table.data th { background: #161b22; }
.roa-pre { white-space: pre-wrap; background: #161b22; border: 1px solid var(--border); padding: 1rem; border-radius: 6px; font-size: 0.82rem; }
.details-body { margin-top: 0.5rem; }
details { margin: 0.75rem 0; }
summary { cursor: pointer; color: var(--info); }
.muted { color: var(--muted); }
"""

    section2 = _scenario_description_prose(config)

    section6 = """
<p class="muted">This batch sample does not track long-lived entities (positions, claims, sessions)
across scenarios. Each scenario row is an independent transaction decision; use Section 4 and
Section 5 for per-scenario traces.</p>
"""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>32_fraud_gate — audit report</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">
  <h1>32_fraud_gate — classic + scenarios.yaml</h1>
  <p class="meta">Generated (UTC): <code>{_esc(start_ts)}</code> — Run status: <strong>{_esc(run_status)}</strong>
  {f' — SIMULATION_END status: {_esc(sim_end_status)}' if sim_end_status else ''}</p>
  <p>Simulation ID: <code>{_esc(simulation_id)}</code></p>

  <h2>Section 1 — Run header and summary</h2>
  <div class="grid">
    <div class="card">Scenarios processed<br/><strong>{len(decisions)}</strong> / {scenario_count}</div>
    <div class="card">Elapsed (s)<br/><strong>{elapsed_sec:.2f}</strong></div>
    <div class="card">Telemetry rows (this run)<br/><strong>{len(run_ev)}</strong></div>
    <div class="card">LLM backend<br/><strong>{_esc(llm_backend)}</strong></div>
  </div>
  <p class="meta">Event counts: {_esc(dict(counts))}</p>
  <h3>Agent registry (end of run)</h3>
  {reg_summary_ul}

  <h2>Section 2 — What this run demonstrates</h2>
  {section2}

  <h2>Section 3 — Charts</h2>
  <p class="muted">No charts for this gate sample (Section 4 table and Section 5 traces carry the
  quantitative and qualitative audit view).</p>

  <h2>Section 4 — Per-scenario trace</h2>
  <table class="data">
    <thead>
      <tr>
        <th>#</th><th>DFID</th><th>Scenario</th><th>tx_id</th><th>amount</th><th>geo</th>
        <th>DIM</th><th>Executed</th><th>vs expected</th><th>Details</th>
      </tr>
    </thead>
    <tbody>
      {"".join(trace_rows) if trace_rows else "<tr><td colspan='10' class='muted'>No AGENT_DECISION rows.</td></tr>"}
    </tbody>
  </table>

  <h2>Section 5 — ROA decision cycle reconstruction</h2>
  {"".join(roa_blocks) if roa_blocks else "<p class='muted'>No decisions to reconstruct.</p>"}

  <h2>Section 6 — Entity lifecycle</h2>
  {section6}

  <h2>Section 7 — Kernel artefacts</h2>
  {kernel}
</div>
</body>
</html>
"""
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path


def _load_bundle_for_cli(config_path: Path) -> Tuple[StorageBundle, Dict[str, Any]]:
    config = load_yaml_config(config_path)
    bundle = materialize_storage_bundle(config, config_path=str(config_path))
    return bundle, config


def main() -> None:
    sample_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Regenerate fraud_gate HTML report from audit storage.")
    parser.add_argument("--simulation-id", default="", help="Filter run (default: latest SIMULATION_START)")
    parser.add_argument("--output-path", default="", help="Write HTML to this path")
    parser.add_argument(
        "--config",
        default=str(sample_dir / "config.yaml"),
        help="Path to config.yaml (SQLite path resolved relative to it)",
    )
    args = parser.parse_args()
    cfg_path = Path(args.config).resolve()
    bundle, config = _load_bundle_for_cli(cfg_path)
    all_ev = bundle.decision_audit.all_events_chronological()
    sim_id = args.simulation_id.strip() or _latest_simulation_id(all_ev) or ""
    if not sim_id:
        raise SystemExit("No SIMULATION_START event found; run the sample first or pass --simulation-id.")

    run_ev = _events_for_latest_simulation_window(all_ev, sim_id)
    dec_n = sum(1 for e in run_ev if e.get("event") == "AGENT_DECISION")
    dest = Path(args.output_path).resolve() if args.output_path.strip() else None
    end_ev = next(
        (e for e in reversed(run_ev) if e.get("event") == "SIMULATION_END"),
        None,
    )
    end_status = str((end_ev.get("details") or {}).get("status", "")) if end_ev else "regenerated"
    path = write_fraud_gate_html_report(
        bundle,
        simulation_id=sim_id,
        sample_dir=sample_dir,
        config=config,
        scenario_count=dec_n,
        elapsed_sec=0.0,
        run_status=end_status,
        output_path=dest,
    )
    print(path)


if __name__ == "__main__":
    main()
