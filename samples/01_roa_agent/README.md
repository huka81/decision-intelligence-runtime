# 01 - ROA Agent (Full Lifecycle Example)

**Goal:** Complete Responsibility-Oriented Agent demonstrating:
- **Responsibility Contract** with mission, authority boundaries, escalation triggers (§3.1-3.3)
- **Long-lived agents** with state and decision trajectory memory (§3.4)
- **Decision lifecycle**: Explain → Policy → Self-Check → Policy Proposal (§4)
- **Dynamic Agents**: InstrumentAgent (class-level) spawning PositionAgent (instance-level) (§6)
- **Escalation paths** when authority limits are reached (§5.3)

**ROA/DIR Alignment:** ROA Manifesto §3-4, §5.3, §6

## ROA Concepts Demonstrated

| Concept | Manifesto Section | Implementation |
|---------|-------------------|----------------|
| Responsibility Contract | §3.1 | `ResponsibilityContract` with `mission`, `authorized_instruments`, `allowed_policy_types`, `escalate_on_uncertainty`, `max_drawdown_limit` |
| Mission | §3.2 | Each agent has explicit mission string guiding interpretation |
| **Mission-Driven Reasoning** | §3.2 | `parse_mission_focus()` extracts weights from mission keywords, `explain()` adjusts thresholds based on mission |
| Authority Boundaries | §3.3 | `allowed_policy_types`, `authorized_instruments` validated in self-check |
| Long-Lived State | §3.4 | `AgentState` with `decision_trajectory`, persists across decisions |
| **Policy Versioning** | §3.4 | `policy_version` in `AgentState`, `update_policy_version()` and `should_shift_strategy()` for adaptive evolution |
| Explain Stage | §4.1 | `explain()` method interprets context into `ExplainResult` |
| Policy Stage | §4.2 | `formulate_policy()` creates `Policy` with justification and confidence |
| Self-Check | §4.3 | `self_check()` validates policy against boundaries, triggers escalation |
| Policy Proposal | §4.4 | `emit_proposal()` creates structured `PolicyProposal` for Runtime |
| Dynamic Agents | §6.1 | `InstrumentAgent.spawn_position_agent()` creates instance-level agents |
| Agent Hierarchy | §6.2 | `parent_agent_id` links PositionAgent to InstrumentAgent |
| Escalation | §5.3 | `EscalationRequest` emitted when confidence < threshold |
| State Persistence | §3.4 | `save_state()` / `load_state()` for JSON file I/O, `to_dict()` / `from_dict()` for serialization |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    InstrumentAgent (class-level)            │
│  Mission: "Interpret signals for BTC-USD"                   │
│  Role: STRATEGIST                                           │
├─────────────────────────────────────────────────────────────┤
│  Explain → Policy → Self-Check → Proposal/Escalation        │
│                          │                                  │
│                          ▼                                  │
│           ┌─────────────────────────────┐                   │
│           │   spawn_position_agent()    │                   │
│           └─────────────────────────────┘                   │
│                          │                                  │
│              ┌───────────┴───────────┐                      │
│              ▼                       ▼                      │
│  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │ PositionAgent       │  │ PositionAgent       │          │
│  │ (instance POS_001)  │  │ (instance POS_002)  │          │
│  │ Mission: "Manage    │  │ Mission: "Manage    │          │
│  │  position POS_001"  │  │  position POS_002"  │          │
│  │ Role: EXECUTOR      │  │ Role: EXECUTOR      │          │
│  │ Own state/trajectory│  │ Own state/trajectory│          │
│  └─────────────────────┘  └─────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## How to run

From repo root:

```bash
pip install -e .
python samples/01_roa_agent/run.py
```

## Scenarios Demonstrated

### Scenario A: Normal Flow (High Confidence)
- Market shows breakout above resistance
- InstrumentAgent identifies opportunity with high confidence (0.82)
- Policy Proposal emitted: `OPEN_POSITION`

### Scenario B: Escalation (Low Confidence)
- High volatility market conditions
- InstrumentAgent has low confidence (0.55 < 0.65 threshold)
- EscalationRequest emitted instead of proposal

### Scenario C: Dynamic PositionAgent
- InstrumentAgent spawns PositionAgent for specific position
- PositionAgent has own mission, state, trajectory
- Manages position independently with tighter risk limits

### Scenario D: Risk Limit Breach
- Position drawdown exceeds max_drawdown_limit (3%)
- PositionAgent mandates CLOSE with high confidence (0.95)
- Agent retired after position closed

### Scenario E: State Persistence
- InstrumentAgent state saved to JSON file (`data/btc_agent_state.json`)
- Agent restored from file with full decision trajectory
- Restored agent continues making decisions, trajectory preserved
- Demonstrates long-lived agent memory (§3.4)

### Scenario F: Mission-Driven Reasoning
- Two agents analyze the **same market context** but have different missions
- **Growth Agent** (mission: "Maximize alpha...") → higher opportunity_weight (1.5x)
- **Defensive Agent** (mission: "Protect capital...") → higher risk_weight (1.5x)
- Same data produces different decisions: one acts, one escalates
- Demonstrates how mission actively influences interpretation in `explain()`

### Scenario G: Policy Versioning
- Agent faces multiple challenging market conditions (increasing volatility)
- Decision trajectory tracks outcomes including escalations
- After repeated challenges → `should_shift_strategy()` triggers policy version update
- Agent evolves from v1 to v2, becoming more conservative
- Demonstrates adaptive strategy evolution via `policy_version` in `AgentState`

## Expected Output

```
======================================================================
ROA Agent Sample - Full Lifecycle Demonstration
======================================================================

[SCENARIO A] Normal decision flow - breakout opportunity

INFO [DFID=...] Starting Scenario A: Normal flow
INFO [DFID=...] Created InstrumentAgent: instrument_btc_usd, mission='...'
INFO [DFID=...] [instrument_btc_usd] Starting decision cycle
INFO [DFID=...] [instrument_btc_usd] Explain: 2 signals, 0 risks, 2 opportunities
INFO [DFID=...] [instrument_btc_usd] Policy: action='OPEN_POSITION' confidence=0.82
INFO [DFID=...] [instrument_btc_usd] Proposal emitted: kind=OPEN_POSITION confidence=0.82

[RESULT A] PolicyProposal emitted:
  DFID: df-...
  Agent: instrument_btc_usd
  Action: OPEN_POSITION
  Confidence: 0.82
  Justification: Breakout detected with acceptable risk profile

----------------------------------------------------------------------

[SCENARIO B] Low confidence - escalation to human/supervisor

INFO [DFID=...] [instrument_btc_usd] Explain: 1 signals, 1 risks, 0 opportunities
INFO [DFID=...] [instrument_btc_usd] Policy: action='HOLD' confidence=0.55
WARNING [DFID=...] [instrument_btc_usd] Self-check FAILED: Confidence 0.55 below threshold 0.65 (escalate=True)

[RESULT B] EscalationRequest emitted:
  Trigger: uncertainty_threshold
  Severity: MEDIUM

----------------------------------------------------------------------

[SCENARIO C] Dynamic PositionAgent - managing specific position

INFO [DFID=...] Spawned PositionAgent: position_POS_001 (parent=instrument_btc_usd)
INFO [DFID=...] [position_POS_001] Explain: 1 signals, 0 risks, 1 opportunities
INFO [DFID=...] [position_POS_001] Policy: action='TAKE_PROFIT' confidence=0.78

----------------------------------------------------------------------

[SCENARIO D] Position drawdown - risk limit forces action

INFO [DFID=...] [position_POS_001] Explain: 2 signals, 2 risks, 0 opportunities
INFO [DFID=...] [position_POS_001] Policy: action='CLOSE' confidence=0.95
INFO [DFID=...] PositionAgent retired. Trajectory: 2 decisions

======================================================================
[SUMMARY] Agent Decision Trajectories
======================================================================

InstrumentAgent (instrument_btc_usd):
  Total decisions: 2
  [1] DFID=... action=OPEN_POSITION confidence=0.82 outcome=ACCEPTED
  [2] DFID=... action=HOLD confidence=0.55 outcome=ESCALATED

PositionAgent (position_POS_001) - RETIRED:
  Total decisions: 2
  [1] DFID=... action=TAKE_PROFIT confidence=0.78 outcome=ACCEPTED
  [2] DFID=... action=CLOSE confidence=0.95 outcome=ACCEPTED

----------------------------------------------------------------------

[SCENARIO E] State Persistence - Save and Load Agent

INFO [instrument_btc_usd] State saved to samples/01_roa_agent/data/btc_agent_state.json
  Saved agent state to: samples/01_roa_agent/data/btc_agent_state.json
  Trajectory before save: 2 decisions

  --- Simulating restart: loading agent from file ---

INFO [instrument_btc_usd] State loaded from samples/01_roa_agent/data/btc_agent_state.json (trajectory: 2 decisions)
  Restored agent: instrument_btc_usd
  Trajectory restored: 2 decisions

[RESULT E] Restored agent decision:
  Action: OPEN_POSITION
  Confidence: 0.82

  Trajectory after new decision: 3 decisions
  Updated state saved.

  Saved state file content (truncated):
    agent_type: InstrumentAgent
    agent_id: instrument_btc_usd
    decisions in trajectory: 3
```

## Key Takeaways

1. **Responsibility defines behavior**: Agents act within declared boundaries, not arbitrarily
2. **Mission guides interpretation**: The same context is interpreted differently by different missions
3. **Escalation is not failure**: It's essential for bounded responsibility
4. **Dynamic agents enable isolation**: Each position has its own lifecycle and trajectory
5. **Memory enables continuity**: Decision trajectory prevents contradictory decisions
6. **Self-check is a heuristic**: No security value, just noise reduction before Runtime
7. **State persistence enables restarts**: Agent state survives process restarts via JSON serialization
