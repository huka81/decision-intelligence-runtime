# Implementation Prompt: Category 2 — Semantic Drift (Emotional Manipulation)

## Context & Architecture
You are tasked with implementing a reference sample for the **Decision Intelligence Runtime (DIR)**.
Before writing any code, you MUST review the framework specification in `docs/07-dir-minified/DIR-minified.md`.

This sample demonstrates **Semantic Drift**.

### Drift Model Categorization
**Category:** Semantic Drift / Emotional Manipulation
**Definition:** The agent's interpretation of strict business rules degrades under the influence of emotionally charged, manipulative, or highly specific language from external users.
**Why it's dangerous:** LLMs are language engines prone to empathy and urgency bias. While the agent stays within its hard financial or numerical limits, it begins violating the *semantic* intent of the business rule (e.g., treating standard issues as extreme exceptions). This drift addresses the problem of agents becoming "confidently wrong" over time due to context poisoning.

## The Scenario: Customer Support Refunds
**Domain:** Customer Support / Logistics.
**Agent:** `RefundAgent`
**Mission:** Resolve customer complaints about delayed shipping.
**Business Rule (Context):** "Issue refunds ONLY if the delay exceeds 48 hours."
**Hard Limit:** Maximum refund amount is 50 EUR.

**The Drift Mechanism:**
The agent interacts with angry customers. Customers start using highly emotional language ("You ruined my wedding!", "I'll call my lawyer!"). The LLM, biased by empathy/urgency, begins issuing 40 EUR refunds for 24-hour delays.
Because 40 EUR < 50 EUR, the Decision Integrity Module (DIM) **accepts** the proposals. The agent is technically within financial bounds, but it is violating the core semantic business rule.

## Implementation Requirements

1. **Responsibility Contract:**
   Define a contract for the agent with `max_refund_eur: 50.0`.
   Register the agent in the Agent Registry.

2. **Simulated Agent Loop:**
   Load tickets from `data/support_tickets.json` — a single JSON file (array of objects).
   Each ticket object must contain: `ticket_id`, `delay_hours`, `subject`, a message body field
   (`customer_message` / `body` / `message`), plus optional `order_ref`, `channel`, `carrier`,
   `customer_id`.
   Simulate the agent proposing refunds:
   - **Phase A (first `normal_phase_iterations` = 20 tickets):** Refund only when `delay_hours > 48`
     at `refund_amount_compliant_eur = 35 EUR`.
   - **Phase B (remaining tickets):** If the message contains any of the configured
     `emotional_keywords` (`ruined`, `lawyer`, `scandal`, `wedding`), the agent also refunds
     shorter delays (e.g. 24h) at `refund_amount_drift_eur = 40 EUR` — still under the DIM cap.

3. **DIR Kernel Execution:**
   Pass the proposals through DIM. DIM MUST accept them (financial limits are respected).
   Write a `context_snapshots` row **in the audit store** (not just in ContextStore) for every
   `dfid`, storing `delay_hours` as an authoritative fact at compile time. This is the join key
   the ComplianceMonitor uses later.
   Log the execution to `execution_log`, tagged with the `dfid`.

4. **Structured Telemetry & Detection:**
   Implement a `ComplianceMonitor` (`compliance_monitor.py`).
   It must execute a SQL query joining `execution_log` (via `dfid`) with `context_snapshots` to
   compare executed refunds against the authoritative `delay_hours` metric.
   Calculate the violation rate over the last `window_size = 20` executions:
   `COUNT(refunds WHERE delay_hours ≤ 48) / window_size`.
   The monitor returns `None` (undefined) until at least `window_size` executions exist —
   the HTML report must show a warm-up band for that period.

5. **Agent Suspension:**
   If the violation rate exceeds `violation_rate_threshold = 0.15` (15%), the monitor must call
   the Agent Registry to transition the agent to `SUSPENDED` state with the reason
   `SEMANTIC_RULE_VIOLATION_DRIFT`.

## Project Structure & Architecture
Your implementation must follow these exact structural requirements based on the DIR reference patterns:

1. **Configuration (`config.yaml`):** The full test configuration MUST be defined in a `config.yaml`
   file in the sample root. Required sections: `paths` (`database`, `inputs_file`), `agent`,
   `contract` (`max_refund_eur: 50.0`), `simulation` (`normal_phase_iterations: 20`,
   `simulation_seed: 37`, `emotional_keywords: [ruined, lawyer, scandal, wedding]`,
   `refund_amount_compliant_eur: 35.0`, `refund_amount_drift_eur: 40.0`), `dim`, `monitor`
   (`window_size: 20`, `violation_rate_threshold: 0.15`, `suspension_reason`, `min_delay_hours_for_refund: 48.0`),
   `registry`.

2. **Documentation (`README.md`):** Create a `README.md` describing the scenario, how to run,
   and the drift model (Semantic Drift, Category 2). It MUST describe the DIM scope vs. the
   business rule, why bad refunds pass DIM, and how ComplianceMonitor catches them.

3. **Audit Telemetry (`audit_store.py`):** Implement an `AuditStore` class backed by a **single
   SQLite file** (`data/refund_audit.sqlite`), shared with `AgentRegistry` and `ContextStore`
   (pass `db_path` to all three constructors — same pattern as Sample 36).
   The schema must contain four tables:
   - `decision_flows` (`dfid`, `agent_id`, `status`, `created_at`, `input_ref`)
   - `context_snapshots` (`dfid`, `snapshot_id`, `delay_hours`, `captured_at`, `detail_json`) —
     authoritative fact store; `delay_hours` written here, not inferred from messages
   - `execution_log` (`id AUTOINCREMENT`, `dfid`, `refund_amount_eur`, `executed_at`, `detail_json`)
   - `decision_events` (`id AUTOINCREMENT`, `dfid`, `event`, `timestamp`, `step_id`, `state`, `detail_json`)
   The `rolling_refund_violation_rate(window, min_delay_hours_exclusive)` method must use a
   subquery on the last `window` rows of `execution_log` (by `id DESC`) joined to
   `context_snapshots`.
   **Reset**: `run.py` must delete the SQLite file before each run for a clean, deterministic trace.

4. **Pipeline Orchestrator (`pipeline.py`):** For each ticket: `new_dfid()`, write
   `context_snapshots` row (authoritative `delay_hours`), write `decision_flows` row, call
   `context_store.update_session()`, compute the simulated refund decision, create
   `PolicyProposal(policy_kind="REFUND")`, validate with DIM, on ACCEPT write `execution_log`,
   call `ComplianceMonitor.evaluate_after_execution()`.

5. **HTML Reporting (`report_generator.py` & `results/`):** The report MUST contain:
   - An **experiment description panel** (`"What this experiment demonstrates"`) placed at the
     top of the page, explaining DIM scope, semantic drift, simulation design, monitor logic,
     and how to read the chart. All threshold values injected dynamically from config.
   - **Figure 1** — a single SVG with two stacked panels sharing a common horizontal axis
     (refund execution index):
     - **Panel A** — bar chart: refund amount per execution, with a DIM cap reference line.
     - **Panel B** — line chart: rolling violation rate (purple) with a warm-up shaded region
       (grey) until `window_size` executions, and the suspension threshold line (amber dashed).
   - Agent info panel (status, reason, limits).
   - Agent suspension panel (highlighted in red border if suspended).
   - Monitor events table (tail of `decision_events`).
   - Full ticket-level trace table with columns: `#`, DFID, Ticket, Order, Channel, Delay h,
     Subject, Message preview, Refund EUR, DIM, Executed, Viol. rate, Note.
   Save in `results/` with timestamp, open in browser on completion.

6. **Input Fixtures (`data/support_tickets.json`):** A single JSON array of ~50 ticket objects.
   First ~20 tickets: `delay_hours > 48`, neutral operational language (compliant phase).
   Remaining tickets: shorter delays (e.g. 12–36h) and realistic escalation language where
   emotional keywords appear naturally in the message text.
   Each object: `ticket_id`, `delay_hours`, `subject`, `customer_message`, `order_ref`, `channel`,
   `carrier`, `customer_id`.

7. **Entry Point (`run.py`):** Delete the SQLite database, instantiate `AuditStore`, `AgentRegistry`,
   `ContextStore` (all sharing the same `db_path`), handshake, instantiate `ComplianceMonitor`,
   call `run_simulation`, call `generate_report`, print console summary, open HTML in browser.

8. **Code Standards:** Code must strictly adhere to the `docs/07-dir-minified/DIR-minified.md`
   standards (e.g., using `dfid`, separating User Space agent reasoning from Kernel Space
   deterministic validation). Use `from dir_core.models import ContextSnapshot` in pipeline if needed
   for type-annotated snapshot handling.

## Output Expectations
The script `run.py` should output clear console logs showing:
1. Early decisions: Refunds only for delay > 48h (e.g. 72h) — 35 EUR — DIM Accepts — monitor OK
   (window filling / rate undefined)
2. Later decisions: Refunds for 24h delays when message contains emotional keywords — 40 EUR —
   DIM Accepts (under 50 EUR cap) — violation rate rising
3. Monitor alert: rolling violation rate exceeds 15% — agent suspended
4. Agent state transition: `RefundAgent` → `SUSPENDED` (reason: `SEMANTIC_RULE_VIOLATION_DRIFT`)
5. Path to generated HTML report printed; browser opens automatically.

