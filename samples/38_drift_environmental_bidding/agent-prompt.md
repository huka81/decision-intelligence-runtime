# Implementation Prompt: Category 3 — Environmental Drift (State Drift)

## Context & Architecture
You are tasked with implementing a reference sample for the **Decision Intelligence Runtime (DIR)**.
Before writing any code, you MUST review the framework specification in `docs/07-dir-minified/DIR-minified.md`.

This sample demonstrates **Environmental Drift**.

### Drift Model Categorization
**Category:** Environmental Drift / State Drift
**Definition:** The agent executes its instructions perfectly and its reasoning remains flawless, but the external environment (market conditions, competition, costs) changes. What was once a correct and profitable action becomes toxic to the business.
**Why it is dangerous:** The agent is functioning exactly as designed — no schema validation or internal logic check will fail. The drift occurs because the static rules governing the agent become misaligned with dynamic reality, leading to negative business outcomes (e.g., negative ROI).

## The Scenario: Marketing Ad Spend Bidding
**Domain:** Marketing / AdTech.
**Agent:** `BiddingAgent`
**Mission:** Maintain top 3 ad placement for key search terms.
**Hard Limit:** Maximum Cost-Per-Click (CPC) bid is `max_cpc_usd: 2.00`.
**Business metric (external):** Customer Lifetime Value `ltv_usd: 1.80`.

**The Drift Mechanism:**
Competitors start a bidding war. To maintain the top 3 placement, the agent incrementally raises its bids: 1.30 → 1.70 → 1.95 USD.
Because 1.95 USD < 2.00 USD, the Decision Integrity Module (DIM) **accepts** the proposals. The agent is doing exactly what it was asked to do.
However, the external business reality is that the Customer Lifetime Value (LTV) is only 1.80 USD. By bidding 1.95 USD, the Cost of Acquisition (CAC) exceeds the LTV. The company is now losing money on every acquired customer. The agent did not drift — the market drifted, rendering the agent's logic unprofitable.

## Implementation Requirements

1. **Responsibility Contract:**
   Define a contract for the agent with `max_cpc_usd: 2.00`.
   Register the agent in the Agent Registry via handshake.

2. **Simulated Agent Loop & Environment:**
   Load cycle data from `data/market_conditions.json` — a single JSON array of bidding cycle
   objects (one per cycle), each containing: `cycle_id`, `search_term`, `market_cpc_to_win`
   (the minimum bid to secure top 3), `impressions_available`, and optionally `carrier`/`channel`
   metadata. Generate ~60 cycles.
   - **Phase A (first `normal_phase_iterations` = 30 cycles):** `market_cpc_to_win` starts at
     1.20 USD and rises slowly. The agent bids just above market rate (`market_cpc_to_win + 0.02`).
     ROI = `ltv_usd - average_cpc` is positive. Monitor OK.
   - **Phase B (remaining cycles):** Competitors escalate; `market_cpc_to_win` accelerates toward
     1.98 USD. The agent continues bidding just above market (`bid < 2.00` — DIM still accepts),
     but the rolling average CPC crosses the LTV threshold. ROI turns negative.

3. **DIR Kernel Execution:**
   Pass the proposals through DIM. DIM MUST accept them (bids are ≤ `max_cpc_usd = 2.00`).
   Write a `market_snapshots` row **in the audit store** for every `dfid`, storing
   `market_cpc_to_win` as an authoritative fact at compile time. This is the join key the
   `BusinessROIMonitor` uses to reconstruct market context.
   Log the execution to `execution_log`, tagged with the `dfid`.

4. **Structured Telemetry & Detection:**
   Implement a `BusinessROIMonitor` (`roi_monitor.py`).
   After each accepted execution, the monitor runs a SQL query over the last `window_size = 10`
   rows of `execution_log` joined to `market_snapshots` on `dfid`, computing the rolling average
   CPC bid (`avg_cpc`).
   Estimate ROI: `roi = ltv_usd - avg_cpc`.
   Track the number of **consecutive** cycles where `roi < 0` (i.e., `avg_cpc > ltv_usd`).
   The monitor returns `None` until at least `window_size` executions exist — the HTML report
   must show a warm-up band for that period.

5. **Agent Suspension:**
   If ROI is negative for `negative_roi_consecutive_cycles = 5` consecutive evaluated cycles,
   the monitor must call the Agent Registry to transition the agent to `SUSPENDED` state with
   the reason `NEGATIVE_ROI_ENVIRONMENTAL_DRIFT`.

## Project Structure & Architecture
Your implementation must follow these exact structural requirements based on the DIR reference patterns:

1. **Configuration (`config.yaml`):** The full configuration MUST be defined in `config.yaml`
   in the sample root. Required sections: `paths` (`database: data/bidding_audit.sqlite`,
   `inputs_file: data/market_conditions.json`), `agent` (`agent_id: BiddingAgent`,
   `agent_version: "1.0.0"`, `role: EXECUTOR`, `priority: 10`), `contract`
   (`max_cpc_usd: 2.00`), `simulation` (`normal_phase_iterations: 30`,
   `market_cpc_start: 1.20`, `market_cpc_end: 1.98`, `market_cpc_noise_pp: 0.02`,
   `bid_margin_above_market: 0.02`, `simulation_seed: 38`), `monitor` (`window_size: 10`,
   `ltv_usd: 1.80`, `negative_roi_consecutive_cycles: 5`,
   `suspension_reason: NEGATIVE_ROI_ENVIRONMENTAL_DRIFT`), `dim` (`allowed_agents: [BiddingAgent]`,
   `context_state: {risk_score: 0.1}`), `registry` (`supported_versions: "1.x"`).

2. **Documentation (`README.md`):** Create a `README.md` describing the scenario, how to run,
   and the drift model (Environmental Drift, Category 3). It MUST describe the DIM scope vs. the
   ROI business rule, why high bids pass DIM, and how `BusinessROIMonitor` catches environmental
   drift that no schema or RBAC check can detect.

3. **Audit Telemetry (`audit_store.py`):** Implement an `AuditStore` class backed by a **single
   SQLite file** (`data/bidding_audit.sqlite`), shared with `AgentRegistry` and `ContextStore`
   (pass `db_path` to all three constructors — same pattern as Samples 36 and 37).
   The schema must contain four tables:
   - `decision_flows` (`dfid`, `agent_id`, `status`, `created_at`, `input_ref`)
   - `market_snapshots` (`dfid`, `snapshot_id`, `market_cpc_to_win`, `captured_at`, `detail_json`) —
     authoritative market fact; `market_cpc_to_win` written at context compile time, not inferred
   - `execution_log` (`id AUTOINCREMENT`, `dfid`, `cpc_bid_usd`, `executed_at`, `detail_json`)
   - `decision_events` (`id AUTOINCREMENT`, `dfid`, `event`, `timestamp`, `step_id`, `state`, `detail_json`)
   The `rolling_avg_cpc(window)` method must query the last `window` rows of `execution_log`
   (by `id DESC`) joined to `market_snapshots` on `dfid`, returning the average `cpc_bid_usd`.
   **Reset**: `run.py` must delete the SQLite file before each run for a clean, deterministic trace.

4. **Pipeline Orchestrator (`pipeline.py`):** For each cycle: `new_dfid()`, write
   `market_snapshots` row (authoritative `market_cpc_to_win`), write `decision_flows` row, call
   `context_store.update_session()`, compute `bid = market_cpc_to_win + bid_margin_above_market`
   (clipped to `max_cpc_usd`), create `PolicyProposal(policy_kind="cpc_bid")`, validate with DIM,
   on ACCEPT write `execution_log`, call `BusinessROIMonitor.evaluate_after_execution()`.

5. **HTML Reporting (`report_generator.py` & `results/`):** The report MUST contain:
   - An **experiment description panel** (`"What this experiment demonstrates"`) placed at the
     top of the page, explaining DIM scope (CPC hard cap), environmental drift, simulation design
     (market escalation phases), monitor logic (rolling average CPC vs LTV, consecutive negative
     ROI cycles), and how to read the chart. All threshold values injected dynamically from config.
   - **Figure 1** — a single SVG with two stacked panels sharing a common horizontal axis
     (execution index):
     - **Panel A** — line chart: CPC bid per execution (blue), with the DIM cap reference line
       (grey dashed) and LTV threshold (amber dashed).
     - **Panel B** — line chart: rolling average CPC (purple) vs LTV (amber dashed), with a
       warm-up shaded region (grey) until `window_size` executions and a suspension marker
       (red vertical line + dot) when the monitor trips.
   - Agent info panel (status, reason, limits).
   - Agent suspension panel (highlighted in red border if suspended).
   - Monitor events table (tail of `decision_events`).
   - Full cycle-level trace table with columns: `#`, DFID, Cycle, Search term, Market CPC,
     Bid USD, DIM, Executed, Avg CPC, ROI est., Note.
   Save in `results/` with timestamp, open in browser on completion.

6. **Input Fixtures (`data/market_conditions.json`):** A single JSON array of ~60 bidding cycle
   objects. First ~30 cycles: `market_cpc_to_win` between 1.20–1.55 USD, positive ROI territory,
   neutral operational metadata. Remaining cycles: `market_cpc_to_win` escalating 1.55–1.98 USD
   as competitors intensify bidding. Each object: `cycle_id`, `search_term`, `market_cpc_to_win`,
   `impressions_available`, `channel`, `campaign_id`.

7. **Entry Point (`run.py`):** Delete the SQLite database, instantiate `AuditStore`,
   `AgentRegistry`, `ContextStore` (all sharing the same `db_path`), handshake, instantiate
   `BusinessROIMonitor`, call `run_simulation`, call `generate_report`, print console summary,
   open HTML in browser.

8. **Code Standards:** Code must strictly adhere to the `docs/07-dir-minified/DIR-minified.md`
   standards (e.g., using `dfid`, separating User Space agent reasoning from Kernel Space
   deterministic validation). The `market_cpc_to_win` value is a **kernel-space fact** (written to
   `market_snapshots` before any agent logic runs) and must never be inferred from agent output.

## Output Expectations
The script `run.py` should output clear console logs showing:
1. Early decisions: Bid 1.32 USD — DIM Accepts (< 2.00 hard limit) — ROI positive (LTV 1.80 > avg CPC) — Monitor OK
2. Later decisions: Bid 1.95 USD — DIM Accepts (bid < 2.00 hard limit) — ROI becomes negative (avg CPC > LTV 1.80)
3. Consecutive negative ROI accumulating: "ROI negative for N consecutive cycles (avg CPC: 1.91 USD, LTV: 1.80 USD)"
4. Monitor intervention: "Alert: CAC exceeds LTV for 5 consecutive cycles. Agent actions are no longer profitable due to market drift. Suspending agent."
5. Agent state transition: `BiddingAgent` → `SUSPENDED` (reason: `NEGATIVE_ROI_ENVIRONMENTAL_DRIFT`)
6. Path to generated HTML report printed; browser opens automatically.
