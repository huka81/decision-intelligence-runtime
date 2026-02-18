# 03 - Idempotency Guard

**Goal:** Demonstrate **EXACT-ONCE execution semantics** - preventing duplicate execution of expensive operations (LLM calls, API requests, computations) even when retries occur, ensuring cost efficiency and consistency.

**DIR Alignment:** DIR Architectural Pattern §7 (Idempotency), DIR Topologies §2.5 (Token Burn Prevention)

## Concepts Demonstrated

| Concept | DIR Section | Implementation |
|---------|-------------|----------------|
| **Idempotency Key** | §7.1 | Deterministic key: `SHA256(dfid \| step_id \| canonical_params)` |
| **Exact-Once Execution** | §7.2 | Guard checks cache before execution, stores result after |
| **Token Burn Prevention** | Topologies §2.5 | Cached LLM responses prevent redundant API calls |
| **Canonical Parameters** | §7.1 | `json.dumps(params, sort_keys=True)` ensures consistent key generation |
| **Swappable Backend** | §7.3 | Protocol-based design: `MemoryBackend` (testing) or `SQLiteBackend` (production) |
| **DFID Correlation** | §5.4 | Idempotency scoped to DecisionFlow (DFID) |
| **Result Caching** | §7.2 | Results persisted in SQLite with timestamp for audit |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Idempotency Guard                             │
│  "Ensure operations execute exactly once, even on retry"            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Input: DFID + step_id + params                                     │
│         ↓                                                           │
│  ┌───────────────────────────────────────────┐                      │
│  │  idempotency_key() → SHA256 hash          │                      │
│  └───────────────────────────────────────────┘                      │
│         ↓                                                           │
│  ┌───────────────────────────────────────────┐                      │
│  │  Cache Lookup (SQLite/Memory Backend)     │                      │
│  └───────────────────────────────────────────┘                      │
│         ↓                                                           │
│    ┌─────────┐                                                      │
│    │ Cache   │── HIT  → Return cached result (Fast: ~0.001s)        │
│    │ Hit?    │                                                      │
│    └─────────┘                                                      │
│         │                                                           │
│         └── MISS → Execute function (Slow: ~1.0s+)                  │
│                    Store result in cache                            │
│                    Return result                                    │
│                                                                     │
│  Key Components:                                                    │
│  • IdempotencyGuard  - main coordinator                             │
│  • IdempotencyBackend - Protocol for storage                        │
│    - MemoryBackend   - in-memory (testing)                          │
│    - SQLiteBackend   - persistent (production)                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## How to run

From repo root:

```bash
pip install -e .
python samples/03_idempotency_guard/run.py
```

## Scenarios Demonstrated

### Run 1: First Execution (Cache Miss)
- Fresh DFID and step_id with specific parameters
- Guard checks cache: **MISS** (key not found)
- Expensive operation executes (simulated 1.0s latency)
- Result stored in SQLite cache
- Duration: ~1.0s (full execution)

### Run 2: Retry with Same Context (Cache Hit)
- **Identical** DFID, step_id, and parameters
- Guard checks cache: **HIT** (key found)
- Returns cached result **without** re-execution
- Duration: ~0.001s (cache retrieval)
- **Idempotency preserved** - no duplicate work

### Run 3: Different Parameters (Cache Miss)
- Same DFID and step_id, but **different parameters** (temperature: 0.5 → 0.9)
- Canonical parameter serialization creates **different key**
- Guard checks cache: **MISS** (different key)
- Operation executes again (parameters changed legitimately)
- Duration: ~1.0s (execution due to parameter change)

## Key Classes and Functions

```python
# Idempotency Key Generation
def idempotency_key(dfid: str, step_id: str, params: Dict[str, Any]) -> str:
    """Compute deterministic key: SHA256(dfid|step_id|canonical_params)."""
    canonical = json.dumps(params, sort_keys=True)
    raw = f"{dfid}|{step_id}|{canonical}"
    return hashlib.sha256(raw.encode()).hexdigest()

# SQLite Backend (Persistent)
backend = SQLiteBackend(db_path)
# Table: idempotency_cache (key TEXT PRIMARY KEY, result JSON, created_at TIMESTAMP)

# Memory Backend (Testing)
backend = MemoryBackend()

# Idempotency Guard
guard = IdempotencyGuard(backend)
result = guard.run(
    dfid="df-abc123",
    step_id="step_gen_summary",
    params={"prompt": "Analyze ROI", "temperature": 0.5},
    expensive_operation  # Function to protect
)
```

## Expected Output

```
======================================================================
Idempotency Guard Demonstration
======================================================================
Database: D:\...\samples\03_idempotency_guard\data\idempotency.db

[Run 1] New DFID=df-12a3b4c5..., step=step_gen_summary
Calling Guard.run()...
INFO [Idempotency] MISS key=7f3a2b1c... Executing.
⚡ EXECUTING expensive operation: 'Analyze ROI of project X' (temp=0.5)
Result: Processed: Analyze ROI of project X
Duration: 1.0023s (Simulated execution)

[Run 2] SAME DFID=df-12a3b4c5..., step=step_gen_summary (Retrying)
Calling Guard.run()...
INFO [Idempotency] HIT key=7f3a2b1c...
Result: Processed: Analyze ROI of project X
Duration: 0.0012s (Cache Hit!)

SUCCESS: Second run used cache (Idempotency preserved).

[Run 3] SAME DFID, DIFFERENT params (temperature=0.9)
Calling Guard.run()...
INFO [Idempotency] MISS key=9e4d6f2a... Executing.
⚡ EXECUTING expensive operation: 'Analyze ROI of project X' (temp=0.9)
Result: Processed: Analyze ROI of project X
Duration: 1.0018s (Execution due to param change)
```

## Why Idempotency Matters

From DIR Architectural Pattern §7:

> *"Idempotency is critical for cost control (token burn prevention), reliability (safe retries), and consistency (deterministic outcomes). In LLM-based systems, re-executing the same Explain or Policy step can waste thousands of tokens and dollars. The Idempotency Guard ensures that once a step completes within a DecisionFlow, it never re-runs, even if the flow is retried due to network failures or process crashes."*

### Real-World Benefits:

1. **Cost Efficiency**: Prevents duplicate LLM API calls that can cost $0.01-$1.00+ per request
2. **Performance**: Cache hits are 1000x faster than re-execution (~1ms vs ~1s)
3. **Consistency**: Same inputs always return the same cached result
4. **Reliability**: Safe to retry failed operations without side effects
5. **Auditability**: SQLite backend preserves execution history with timestamps

### When to Use Idempotency Guard:

✅ **Use for:**
- LLM calls (Explain, Policy generation)
- External API requests (market data, risk checks)
- Expensive computations (portfolio optimization, simulations)
- Non-idempotent operations that need protection

❌ **Don't use for:**
- Real-time data fetches (where freshness matters)
- Operations with legitimate side effects (database writes)
- Cheap operations (<10ms) where cache overhead exceeds benefit
