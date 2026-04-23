"""
HTML audit report for ``34_langchain_roa_wrapper`` (Sample Development Guide §17).

Data source: ``bundle.decision_audit.all_events_chronological()`` plus AgentRegistry
and ContextStore. Regenerate offline: ``python report_generator.py``.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_SAMPLES = _REPO_ROOT / "samples"
_SAMPLE_DIR = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SAMPLES) not in sys.path:
    sys.path.insert(0, str(_SAMPLES))
if str(_SAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(_SAMPLE_DIR))

from dir_core import AgentRegistry, ContextStore
from dir_core.storage import StorageBundle

from shared.bootstrap import materialize_storage_bundle, normalize_database_provider
from shared.config import load_yaml_config

from schemas import FinOpsScenario, load_scenarios


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


def _finops_section2_prose(config: Dict[str, Any]) -> str:
    agents = config.get("agents") or []
    c0 = (agents[0].get("contract") or {}) if agents else {}
    envs = c0.get("allowed_environments", ["DEV", "STG"])
    pol = c0.get("allowed_policy_types", [])
    esc = c0.get("escalate_on_uncertainty", 0.7)
    sim = config.get("simulation") or {}
    run_id = sim.get("run_id", "")
    return f"""
<p>This sample demonstrates a <strong>classic</strong> DIR topology with an external
<strong>LangChain</strong> agent in User Space. The agent must emit a
<code>PolicyProposal</code> (Claim) through ROA stages Explain → Policy → deterministic
Self-Check before any kernel execution. The Decision Integrity Module (<code>validate_proposal</code>)
plus FinOps <code>custom_validators</code> enforce resource existence and authoritative
<code>context_store</code> environment labels — not LLM-invented tags.</p>
<p>Hard-coded thresholds referenced from <code>config.yaml</code> for this narrative:
<code>allowed_environments = {_esc(envs)}</code>,
<code>allowed_policy_types = {_esc(pol)}</code>,
<code>escalate_on_uncertainty = {_esc(esc)}</code> (policies below this confidence never become proposals),
and <code>simulation.run_id = {_esc(run_id)}</code> for telemetry grouping.</p>
<p>Sections 4–5 reconstruct the audit trail from canonical <code>decision_audit_events</code> only.</p>
"""


def _ordered_trace_events(run_ev: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in run_ev:
        ev = str(e.get("event", ""))
        if ev in ("AGENT_DECISION", "FINOPS_SELF_CHECK_FAILED"):
            out.append({"kind": ev, "event": e})
    return out


def _trace_verdict(e: Dict[str, Any]) -> str:
    d = e.get("details") or {}
    if e.get("event") == "FINOPS_SELF_CHECK_FAILED":
        return "SELF_CHECK_FAILED"
    return str(d.get("verdict", ""))


def _expected_match(verdict: str, expected: str) -> bool:
    return verdict.upper().strip() == expected.upper().strip()


def _trace_table_rows(
    trace: List[Dict[str, Any]],
    expected_by_label: Dict[str, str],
    exec_by_dfid: Dict[str, Dict[str, Any]],
) -> str:
    rows: List[str] = []
    for idx, item in enumerate(trace, start=1):
        ev = item["event"]
        d = ev.get("details") or {}
        dfid = str(ev.get("dfid", ""))
        dfid_short = (dfid[:8] + "…") if len(dfid) > 8 else dfid
        label = str(d.get("scenario_label", ""))
        exp = expected_by_label.get(label, "")
        verdict = _trace_verdict(ev)
        vcls = "badge-ok" if verdict == "ACCEPT" else "badge-reject"
        if verdict == "SELF_CHECK_FAILED":
            vcls = "badge-warn"
        match = _expected_match(verdict, exp) if exp else False
        mcls = "badge-ok" if match else "badge-warn"
        rid = str(d.get("resource_id", ""))
        pk = str(d.get("policy_kind", "")) if ev.get("event") == "AGENT_DECISION" else "—"
        executed = bool(d.get("executed", False)) if ev.get("event") == "AGENT_DECISION" else False
        if executed or dfid in exec_by_dfid:
            executed = True
        narrative = str(d.get("explain_narrative", ""))
        justification = str(d.get("justification", ""))
        reason = str(d.get("reason", ""))
        rows.append(
            f"<tr>"
            f"<td>{idx}</td>"
            f"<td><code title=\"{_esc(dfid)}\">{_esc(dfid_short)}</code></td>"
            f"<td>{_esc(label)}</td>"
            f"<td><code>{_esc(rid)}</code></td>"
            f"<td>{_esc(pk)}</td>"
            f"<td><span class=\"{vcls}\">{_esc(verdict)}</span></td>"
            f"<td>{_esc('yes' if executed else 'no')}</td>"
            f"<td><span class=\"{mcls}\">{'match' if match else 'mismatch'}</span> "
            f"(expected {_esc(exp)})</td>"
            f"<td><details><summary>Reasoning</summary><div class=\"details-body\">"
            f"<p><strong>Explain narrative:</strong> {_esc(narrative or '(not recorded)')}</p>"
            f"<p><strong>Justification / policy reason:</strong> {_esc(justification or reason)}</p>"
            f"<p><strong>DIM / self-check reason:</strong> {_esc(reason)}</p>"
            f"</div></details></td>"
            f"</tr>"
        )
    if not rows:
        return "<tr><td colspan='9' class='muted'>No AGENT_DECISION or FINOPS_SELF_CHECK_FAILED.</td></tr>"
    return "".join(rows)


def _roa_block(ev: Dict[str, Any], *, executed: bool, exec_note: str) -> str:
    d = ev.get("details") or {}
    dfid = str(ev.get("dfid", ""))
    evname = str(ev.get("event", ""))
    agent_id = str(d.get("agent_id", ""))
    role = str(d.get("contract_role", ""))
    verdict = _trace_verdict(ev)
    allowed = d.get("contract_allowed_policy_types") or []
    allowed_s = json.dumps(allowed, default=str)
    narrative = str(d.get("explain_narrative", "")) or "(not recorded)"
    signals = d.get("explain_signals") or []
    risks = d.get("explain_risks") or []
    opps = d.get("explain_opportunities") or []
    sc_pass = bool(d.get("self_check_passed", True))
    sc_reas = str(d.get("self_check_reason", ""))
    pk = str(d.get("policy_kind", "")) if evname == "AGENT_DECISION" else "(no proposal)"
    conf = d.get("confidence", "")
    reason_dim = str(d.get("reason", ""))
    sc_line = _esc(sc_reas if evname != "FINOPS_SELF_CHECK_FAILED" else reason_dim)
    inner = f"""
<pre class="roa-pre">
DFID: {_esc(dfid)}
Agent: {_esc(agent_id)}  Role: {_esc(role)}  Event: {_esc(evname)}

[EXPLAIN]
  Narrative:   {_esc(narrative)}
  Signals:     {_esc(signals)}
  Risks:       {_esc(risks)}
  Opportunities: {_esc(opps)}

[POLICY]
  Proposed action:  {_esc(pk)}
  Confidence:       {_esc(conf)}
  Justification:    {_esc(d.get("justification", ""))}

[SELF-CHECK]
  Passed: {"yes" if sc_pass else "no"}
  Reason (if failed): {sc_line}

[DIM VALIDATION]
  Verdict:  {_esc(verdict)}
  Reason:   {_esc(reason_dim)}
  Contract: role={_esc(role)}  allowed_policy_types={_esc(allowed_s)}

[EXECUTION]
  Executed: {"yes" if executed else "no"}
  Side effect: {_esc(exec_note)}
</pre>
"""
    lab = str(d.get("scenario_label", "row"))
    return f"""
<details>
  <summary><strong>ROA trace — {_esc(lab)}</strong></summary>
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
                "<td>Lifecycle transition in canonical store.</td>"
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
            '<p class="muted">No rows in <code>flow_transitions</code> '
            "(this sample does not record lifecycle transitions).</p>"
        )

    ctx_rows = []
    for dfid in dfids[:80]:
        sess = store.get_session(dfid)
        idle = sess.get("idle_resources") if isinstance(sess, dict) else {}
        inst = idle.get("instances", []) if isinstance(idle, dict) else []
        n_inst = len(inst) if isinstance(inst, list) else 0
        ctx_rows.append(
            "<tr>"
            f"<td><code>{_esc(dfid)}</code></td>"
            f"<td>{len(sess) if isinstance(sess, dict) else 0}</td>"
            f"<td>{_esc(sess.get('scenario_label', ''))}</td>"
            f"<td>{n_inst}</td>"
            f"<td>{_esc(sess.get('trust_input_labels', ''))}</td>"
            "</tr>"
        )
    ctx_html = (
        "<table class='data'><thead><tr>"
        "<th>dfid</th><th>session keys</th><th>scenario_label</th>"
        "<th>idle instance count</th><th>trust_input_labels</th>"
        "</tr></thead><tbody>"
        + ("".join(ctx_rows) if ctx_rows else "<tr><td colspan='5' class='muted'>(none)</td></tr>")
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
    <h4>Context store sessions</h4>
    {ctx_html}
  </div>
</details>
"""


def write_finops_langchain_html_report(
    bundle: StorageBundle,
    *,
    simulation_id: str,
    sample_dir: Path,
    config: Dict[str, Any],
    scenario_yaml_count: int,
    elapsed_sec: float,
    run_status: str,
    output_path: Optional[Path] = None,
) -> Path:
    all_ev = bundle.decision_audit.all_events_chronological()
    run_ev = _events_for_latest_simulation_window(all_ev, simulation_id)
    slug = f"{scenario_yaml_count}scenarios"
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
    trace = _ordered_trace_events(run_ev)
    scenarios_path = sample_dir / "scenarios.yaml"
    scenarios: List[FinOpsScenario] = (
        load_scenarios(scenarios_path) if scenarios_path.is_file() else []
    )
    expected_by_label = {s.label: s.expected for s in scenarios}

    exec_by_dfid: Dict[str, Dict[str, Any]] = {}
    for e in run_ev:
        if e.get("event") == "FINOPS_EXECUTION":
            exec_by_dfid[str(e.get("dfid", ""))] = e

    trace_rows_html = _trace_table_rows(trace, expected_by_label, exec_by_dfid)

    roa_blocks: List[str] = []
    for item in trace:
        ev = item["event"]
        dfid = str(ev.get("dfid", ""))
        d = ev.get("details") or {}
        ex = exec_by_dfid.get(dfid)
        did_exec = bool(d.get("executed")) or bool(ex)
        if ex:
            xd = ex.get("details") or {}
            note = (
                f"Dry-run FINOPS_EXECUTION resource_id={xd.get('resource_id')} "
                f"idempotency_key={str(xd.get('idempotency_key', ''))[:16]}…"
            )
        else:
            if str(d.get("verdict", "")).upper() == "ACCEPT" and d.get("executed"):
                note = "Dry-run execution recorded (see FINOPS_EXECUTION)."
            else:
                note = "blocked — no execution"
        roa_blocks.append(_roa_block(ev, executed=did_exec, exec_note=note))

    decisions_only = [item["event"] for item in trace if item["kind"] == "AGENT_DECISION"]
    registry = AgentRegistry(storage=bundle.agent_registry)
    reg_list = registry.list_agents()
    agent_fb = reg_list[0] if reg_list else ""
    if not agent_fb and decisions_only:
        agent_fb = str((decisions_only[0].get("details") or {}).get("agent_id", ""))

    kernel = _kernel_section(
        bundle,
        config,
        [str(e.get("dfid", "")) for e in decisions_only],
        agent_fb,
    )

    summary_reg: List[str] = []
    for aid in registry.list_agents() or ([agent_fb] if agent_fb else []):
        st = registry.get_agent_status(aid)
        summary_reg.append(
            f"<li><code>{_esc(aid)}</code> — {_esc(st[0] if st else '?')}"
            f"{(' — ' + _esc(str(st[1]))) if st and st[1] else ''}</li>"
        )
    reg_summary_ul = (
        "<ul>" + "".join(summary_reg) + "</ul>" if summary_reg else "<p class='muted'>(none)</p>"
    )

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
h2 { font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid var(--border);
  padding-bottom: 0.35rem; }
h3 { font-size: 1rem; margin-top: 1.25rem; }
.meta { color: var(--muted); font-size: 0.9rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.75rem; margin: 1rem 0; }
.card { border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; background: #161b22; }
.badge-ok { color: var(--ok); font-weight: 600; }
.badge-reject { color: var(--reject); font-weight: 600; }
.badge-warn { color: var(--warn); font-weight: 600; }
table.data { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 0.75rem 0; }
table.data th, table.data td { border: 1px solid var(--border); padding: 0.45rem 0.5rem;
  text-align: left; vertical-align: top; }
table.data th { background: #161b22; }
.roa-pre { white-space: pre-wrap; background: #161b22; border: 1px solid var(--border);
  padding: 1rem; border-radius: 6px; font-size: 0.82rem; }
.details-body { margin-top: 0.5rem; }
details { margin: 0.75rem 0; }
summary { cursor: pointer; color: var(--info); }
.muted { color: var(--muted); }
figcaption { font-size: 0.85rem; margin-top: 0.5rem; }
"""

    section2 = _finops_section2_prose(config)
    section6 = """
<p class="muted">This batch sample does not track persistent FinOps entities across scenarios.
Each row is an independent decision flow; use Sections 4–5 for traces.</p>
"""

    n_decisions = sum(1 for e in run_ev if e.get("event") == "AGENT_DECISION")

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>34_langchain_roa_wrapper — audit report</title>
  <style>{css}</style>
</head>
<body>
<div class="wrap">
  <h1>34_langchain_roa_wrapper — classic + LangChain ROA</h1>
  <p class="meta">Generated (UTC): <code>{_esc(start_ts)}</code> — Run status:
  <strong>{_esc(run_status)}</strong>
  {f' — SIMULATION_END: {_esc(sim_end_status)}' if sim_end_status else ''}</p>
  <p>Simulation ID: <code>{_esc(simulation_id)}</code></p>

  <h2>Section 1 — Run header and summary</h2>
  <div class="grid">
    <div class="card">Scenarios in YAML<br/><strong>{scenario_yaml_count}</strong></div>
    <div class="card">AGENT_DECISION rows<br/><strong>{n_decisions}</strong></div>
    <div class="card">Elapsed (s)<br/><strong>{elapsed_sec:.2f}</strong></div>
    <div class="card">Telemetry rows (window)<br/><strong>{len(run_ev)}</strong></div>
    <div class="card">LLM backend<br/><strong>{_esc(llm_backend)}</strong></div>
  </div>
  <p class="meta">Event counts: {_esc(dict(counts))}</p>
  <h3>Agent registry (end of run)</h3>
  {reg_summary_ul}

  <h2>Section 2 — What this run demonstrates</h2>
  {section2}

  <h2>Section 3 — Charts</h2>
  <p class="muted">No charts for this sample — Section 4 table and Section 5 traces carry the audit view.</p>

  <h2>Section 4 — Per-scenario trace</h2>
  <table class="data">
    <thead>
      <tr>
        <th>#</th><th>DFID</th><th>Scenario</th><th>resource_id</th><th>policy_kind</th>
        <th>DIM</th><th>Executed</th><th>vs expected</th><th>Details</th>
      </tr>
    </thead>
    <tbody>
      {trace_rows_html}
    </tbody>
  </table>

  <h2>Section 5 — ROA decision cycle reconstruction</h2>
  {"".join(roa_blocks) if roa_blocks else "<p class='muted'>No trace rows.</p>"}

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
    parser = argparse.ArgumentParser(
        description="Regenerate 34_langchain_roa_wrapper HTML report from audit storage.",
    )
    parser.add_argument(
        "--simulation-id",
        default="",
        help="Run id (default: latest SIMULATION_START in DB)",
    )
    parser.add_argument("--output-path", default="", help="Write HTML to this path")
    parser.add_argument(
        "--config",
        default=str(sample_dir / "config.yaml"),
        help="Path to config.yaml",
    )
    args = parser.parse_args()
    cfg_path = Path(args.config).resolve()
    bundle, config = _load_bundle_for_cli(cfg_path)
    all_ev = bundle.decision_audit.all_events_chronological()
    sim_id = args.simulation_id.strip() or _latest_simulation_id(all_ev) or ""
    if not sim_id:
        raise SystemExit("No SIMULATION_START found; run the sample or pass --simulation-id.")

    scenarios = load_scenarios(sample_dir / "scenarios.yaml")
    run_ev = _events_for_latest_simulation_window(all_ev, sim_id)
    dest = Path(args.output_path).resolve() if args.output_path.strip() else None
    end_ev = next(
        (e for e in reversed(run_ev) if e.get("event") == "SIMULATION_END"),
        None,
    )
    end_status = str((end_ev.get("details") or {}).get("status", "")) if end_ev else "regenerated"
    t0 = time.perf_counter()
    path = write_finops_langchain_html_report(
        bundle,
        simulation_id=sim_id,
        sample_dir=sample_dir,
        config=config,
        scenario_yaml_count=len(scenarios),
        elapsed_sec=time.perf_counter() - t0,
        run_status=end_status,
        output_path=dest,
    )
    print(path)


if __name__ == "__main__":
    main()
