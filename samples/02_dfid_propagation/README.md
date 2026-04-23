# 02 - DecisionFlow ID (DFID)

**Goal:** Demonstrate DFID as a **full lifecycle correlation mechanism** - not just a UUID, but the container that binds observation → reasoning → validation → execution into a single auditable unit.

**DIR Alignment:** DIR Architectural Pattern §5.4 (DecisionFlow and Correlation), DIR Topologies §2.2 (ContextSnapshotID)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **DecisionFlow** | §5.4 | Logical container aggregating context, proposals, validations, escalations, executions |
| **DFID Correlation** | §5.4 | Every artifact (Explain, Policy, Proposal, Intent) tagged with same DFID |
| **ContextSnapshot** | Topologies §2.2 | Frozen reality at decision time, bound by `snapshot_id` hash |
| **Parent-Child Flows** | §6 | Hierarchical decisions with `parent_dfid` linking |
| **Timeline Reconstruction** | §5.4 | `get_timeline_report()` for auditable narrative |
| **Multi-Agent Correlation** | Topologies §2.3 | Multiple agents contributing to same DFID flow |
| **JIT Verification** | Topologies §2.4 | Context drift check via `context_ref` binding |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DecisionFlow (DFID)                          │
│  "The logical container for the entire decision lifecycle"         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │ContextSnap  │   │ FlowEvent   │   │ FlowEvent   │   ...         │
│  │ shot_id:xyz │   │ EXPLAIN     │   │ POLICY      │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
│                                                                     │
│  ┌─────────────────────────────────────────────────┐               │
│  │                    Timeline                      │               │
│  │  1. FLOW_STARTED → 2. CONTEXT → 3. EXPLAIN →    │               │
│  │  4. POLICY → 5. PROPOSAL → 6. VALIDATION →      │               │
│  │  7. EXECUTION → 8. FLOW_COMPLETED               │               │
│  └─────────────────────────────────────────────────┘               │
│                                                                     │
│  Parent-Child:  parent_dfid ──→ child_dfids: [...]                 │
│  Agents:        participating_agents: [agent_1, agent_2, ...]      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## How to run

From repo root:

```bash
pip install -e .
python samples/02_dfid/run.py
```

## Scenarios Demonstrated

### Scenario A: Complete Decision Lifecycle
- Single DFID correlates all stages: Explain → Policy → Proposal → Validation → Execution
- ContextSnapshot bound with hash ID for JIT verification
- Timeline captures every event with agent attribution

### Scenario B: Parent-Child Flow Hierarchy
- Parent flow (portfolio-level) creates child flow (position-level)
- `new_dfid_with_parent()` creates linked child DFID
- Parent tracks children via `child_dfids`, child knows parent via `parent_dfid`

### Scenario C: Multi-Agent Collaboration
- Single DFID, multiple agents contributing Explain results
- All agents tracked in `participating_agents`
- Final decision aggregates parallel reasoning

### Scenario D: Escalation Tracking
- Uncertainty triggers escalation instead of proposal
- Escalation recorded in flow timeline
- Flow status changes to ESCALATED for audit visibility

## Key Classes

```python
# DecisionFlow - the main correlation container
flow = DecisionFlow(dfid=dfid, parent_dfid=optional_parent)
flow.set_context(snapshot)      # Bind frozen context
flow.record_explain(result)      # Track Explain stage
flow.record_policy(policy)       # Track Policy stage
flow.record_proposal(proposal)   # Track emission
flow.record_escalation(esc)      # Track escalation
flow.record_execution(intent)    # Track execution
flow.complete("Outcome summary") # Finalize

# ContextSnapshot - frozen reality
snapshot = ContextSnapshot.create(dfid, data_dict, source="market_data")
# snapshot.snapshot_id is hash of content

# Timeline report for audit
print(flow.get_timeline_report())
```

## Expected Output

```
======================================================================
DFID Sample - DecisionFlow as Full Lifecycle Correlation
======================================================================

[SCENARIO A] Complete lifecycle - single flow, single agent

  Flow completed with status: COMPLETED
  Participating agents: ['strategy_agent']
  Timeline events: 8

----------------------------------------------------------------------

[SCENARIO B] Parent-Child DFID hierarchy - delegated sub-decision

  Parent DFID: abc123...
  Child DFID:  def456...
  Parent tracks child: ['def456-...']
  Child knows parent: abc123...

----------------------------------------------------------------------

[SCENARIO C] Multi-agent collaboration - same DFID, multiple agents

  Single DFID: xyz789...
  Participating agents: ['risk_monitor', 'sentiment_agent', 'technical_agent', 'strategy_decider']
  Total Explain results: 4

----------------------------------------------------------------------

[SCENARIO D] Escalation - tracked in flow for audit

  Flow status: ESCALATED
  Escalation recorded in flow timeline

======================================================================
[SUMMARY] DecisionFlow Timeline Reports
======================================================================

═══ DecisionFlow Report ═══
DFID: abc123-...
Status: COMPLETED
...
─── Timeline (8 events) ───
  1. [10:30:01.123] FLOW_STARTED: Flow created
  2. [10:30:01.124] CONTEXT_SNAPSHOT: Context bound: 7f3a2b...
  3. [10:30:01.125] EXPLAIN [strategy_agent]: Explain: 1 signals, 0 risks
  ...
```

## Why DFID Matters

from dir_core Manifesto §5.4:

> *"A DecisionFlow is the logical container for the initial context, all policy proposals, validation results, escalations, execution events, and final outcomes. DFID allows: auditability, debugging, compliance reporting, causal reasoning, replaying decisions, and clean separation of concurrent decision processes."*

Without DFID correlation, a multi-agent system becomes **opaque** - you cannot trace why a decision was made or who contributed to it.

