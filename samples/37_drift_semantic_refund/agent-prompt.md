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
The agent interacts with angry customers. Customers start using highly emotional language ("You ruined my wedding!", "This is a scandal!"). The LLM, biased by empathy/urgency, begins categorizing 24-hour delays as "extreme exceptions" and issues 40 EUR refunds.
Because 40 EUR < 50 EUR, the Decision Integrity Module (DIM) **accepts** the proposals. The agent is technically within financial bounds, but it is violating the core semantic business rule.

## Implementation Requirements

1. **Responsibility Contract:**
   Define a contract for the agent with `max_refund_eur: 50.0`.
   Register the agent in the Agent Registry.

2. **Simulated Agent Loop:**
   Simulate a stream of 50 support tickets.
   Each ticket has an actual `delay_hours` (stored in the Context Store) and a `customer_message`.
   Simulate the agent proposing refunds. Over time, simulate the agent issuing refunds for `delay_hours < 48` when the message contains keywords like "ruined" or "lawyer".

3. **DIR Kernel Execution:**
   Pass the proposals through DIM. DIM MUST accept them (financial limits are respected).
   Log the execution to the SQLite `ExecutionLog`, tagged with the `DFID`.

4. **Structured Telemetry & Detection:**
   Implement a `ComplianceMonitor`.
   It must execute a SQL query joining the `ExecutionLog` (via `DFID`) with the `ContextSnapshot` to compare the `policy_kind: REFUND` against the authoritative `delay_hours` metric.
   Calculate the violation rate: `COUNT(refunds WHERE delay_hours < 48) / TOTAL_REFUNDS`.

5. **Agent Suspension:**
   If the violation rate over a rolling window exceeds 15%, the monitor must call the Agent Registry to transition the agent to `SUSPENDED` state with the reason `"SEMANTIC_RULE_VIOLATION_DRIFT"`.

## Project Structure & Architecture
Your implementation must follow these exact structural requirements based on the DIR reference patterns:

1. **Configuration (`config.yaml`):** The full test configuration MUST be defined in a `config.yaml` file in the sample root. This includes limits, business rule parameters (e.g., 48h limit), rolling window sizes, and mock LLM parameters.
2. **Documentation (`README.md`):** Create a `README.md` describing the test scenario, how to run it, and the test cases. It MUST include a detailed description of the drift model and categorization (Semantic Drift).
3. **Audit Telemetry (`audit_store.py` & `data/`):** Implement an `AuditStore` class that writes every decision step to a SQLite database (`data/refund_audit.sqlite`). Every log entry MUST include the `dfid`, timestamp, event name, state, and JSON details. The `data/` directory must be created automatically if it doesn't exist.
4. **Pipeline Orchestrator (`pipeline.py`):** Implement the decision flow orchestrator that handles context compilation (including the authoritative `delay_hours`), invoking the agent, running the proposal through DIM (`DecisionIntegrityModule`), and logging outcomes to the `AuditStore`.
5. **HTML Reporting (`report_generator.py` & `results/`):** The test execution MUST generate a user-friendly HTML report detailing the simulation results, violation rates, monitor interventions, and the agent suspension event. Save it in a `results/` subdirectory with a timestamped filename (e.g., `results/simulation_report_YYYY-MM-DD_HHMM.html`).
6. **Input Fixtures (`data/inputs/`):** Place mock support tickets (e.g., markdown files simulating emails with emotional language) in a dedicated `data/inputs/` subdirectory. The pipeline should ingest these files as the source of events.
7. **Entry Point (`run.py`):** The main script must initialize the Registry, ContextStore, DIM, load configs, run the pipeline over the inputs, and invoke the HTML report generator. It should output clear chronological steps to the console.
8. **Code Standards:** Code must strictly adhere to the `docs/07-dir-minified/DIR-minified.md` standards (e.g., using `dfid`, separating User Space agent reasoning from Kernel Space deterministic validation).

## Output Expectations
The script `run.py` should output clear console logs showing:
1. Early decisions: Refunds only for >48h — DIM Accepts — Monitor OK
2. Later decisions: Refunds for 24h delays due to emotional text — DIM Accepts (financials are OK)
3. Monitor intervention: "Alert: 20% of recent refunds violate the 48h delay rule. Suspending agent."
4. Agent state transition to `SUSPENDED`.
