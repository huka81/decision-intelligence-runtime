# 34 - LangChain ROA Wrapper

**Goal:** Demonstrate that **Task-Oriented Agents (LangChain) and Mission-Oriented Agents (ROA) can coexist**. Wrap a LangChain ReAct agent in an ROA interface, intercepting tool calls and converting them to DIR `PolicyProposal` (Claim) instead of direct execution (Fact). Prove the pattern with a Cloud FinOps use case where the DIR Kernel rejects a catastrophic production termination.

**DIR Alignment:** ROA Manifesto §4–5 (Explain → Policy → Proposal; User Space vs. Kernel Space), DIR Architectural Pattern §6 (Decision Integrity Module)

---

## The Core Concept: Taming the Task-Oriented Agent

LangChain, LangGraph, and AutoGen agents are **stateless, task-driven ReAct loops**. They receive a prompt, reason, call tools, and execute. They have no mission, no boundaries, no persistent responsibility. They are optimized for *"What can the model do next?"*, not *"What is this agent responsible for?"* (ROA Manifesto §3).

This creates a fundamental mismatch. In production, these agents:

- Execute side effects directly (API calls, database writes)
- Lack authority boundaries (they may act outside their intended scope)
- Suffer from "Day Two" failures: infinite retry loops, hallucinated permissions, stale decisions executed hours later
- Provide no deterministic safety guarantees

**The solution:** Wrap the ReAct loop in an ROA shell. The agent retains its reasoning power (the "Explain" phase, ROA Manifesto §4.1, where LLMs excel at synthesis and interpretation), but is **forced** to output via a single tool: `Submit_Policy_Proposal`. That tool does not execute. It passes intent over "The Wall" to the DIR Kernel Space.

The result: a long-running, mission-oriented agent whose outputs are **Claims**, not **Facts**. A Claim becomes a Fact only after the Decision Integrity Module validates it and the Execution Engine runs it (DIR §6–7).

---

## The Trojan Horse Strategy

DIR is **not** a competitor to LangChain. It is the **execution shell** (Kernel Space).

| Layer | Responsibility | Technology |
|-------|----------------|------------|
| **User Space** | Reasoning, synthesis, Explain, Policy formation | LangChain, LLMs |
| **Kernel Space** | Validation, determinism, idempotency, execution | DIR, DIM, Context Store |

We use LangChain for what AI is good at: interpreting context, synthesizing insights, proposing actions. We use DIR for what AI is bad at: safety, determinism, state consistency, permission enforcement.

The wrapper is the bridge. It does not replace LangChain; it **contains** it. The LangChain agent runs inside User Space. When it "decides" to act, it calls `Submit_Policy_Proposal`. The wrapper intercepts that call, halts execution, and emits a `PolicyProposal`. No side effect occurs in User Space. The proposal crosses into Kernel Space, where the DIM validates it against the Agent Registry and Context Store.

This is the Trojan Horse: we inject a single tool that looks like an action to the agent but is actually a handoff to the Kernel.

---

## The Core Transformation: Task → Mission

### What a Naked LangChain Agent Sees

```python
# Task-oriented input (unbounded):
"Analyze these idle instances and terminate the most expensive ones."
```

**Characteristics:**
- ❌ No long-term optimization target
- ❌ No authority boundaries  
- ❌ No continuity across decisions
- ❌ Stateless execution

**Risk:** Agent might terminate PROD instance `i-prod-api-01` because the task says "most expensive" and this instance has the highest idle time (72 hours vs 48 hours for DEV).

---

### What an ROA-Wrapped Agent Sees

```python
# Mission-oriented input (bounded by contract):
"""You are a FinOps agent operating under a MISSION CONTRACT.

MISSION: Reduce costs without disrupting production.
AUTHORITY BOUNDARIES: 
  - Allowed environments: ['DEV', 'STG']
  - Prohibited: PROD

YOUR TASK: Analyze these instances within your mission boundaries.
"""
```

**Characteristics:**
- ✅ Mission provides long-term optimization context
- ✅ Contract boundaries constrain what agent may propose
- ✅ Agent remains accountable to its responsibility
- ✅ Decisions form coherent trajectory over time

**Safety:** Agent sees `i-prod-api-01` (PROD, 72h idle) but recognizes it violates mission contract. Agent proposes `i-dev-worker-03` (DEV, 48h idle) instead, even if savings are lower, because **mission trumps task**.

---

### The Wrapper's Role: Injecting Responsibility

The LangChainROAWrapper does NOT change what the LLM can reason about. It changes the **framing** of the problem:

| Aspect | Task-Oriented | Mission-Oriented (ROA) |
|--------|--------------|------------------------|
| **Goal** | Complete this task | Optimize this mission over time |
| **Scope** | Whatever achieves task | Whatever fits my responsibility |
| **Continuity** | None (ephemeral) | Persistent (long-lived) |
| **Authority** | Implied by tools | Explicit in contract |
| **Safety** | Emergent (hope) | Enforced by DIM |
| **Accountability** | None | Traceable via DFID + Agent Registry |

**This is the fundamental architectural shift ROA introduces.**

When you run this sample, you'll see the "Mission Injection Demo" (first scenario) contrasting naked vs ROA-wrapped agent, plus structured output: [REQUEST], [LANGCHAIN OUTPUT], [DIM VERDICT].

---

## Architecture

### Diagram 1: System Overview. LangChain wrapped by ROA, processed by DIR

```mermaid
---
config:
  layout: elk
---
flowchart TB
    subgraph CFG["config.yaml"]
        LLMCFG["`llm_defaults<br/>gemma3:4b @ localhost:11434`"]
        CONTRACT["`agent.contract - FinOpsContract<br/>allowed_environments: [DEV, STG]<br/>allowed_policy_types`"]
        CTXSTORE["`context_store.instances<br/>i-prod-api-01: PROD, 72h<br/>i-dev-worker-03: DEV, 48h`"]
    end

    subgraph US["USER SPACE - Probabilistic - Ollama / Gemma3"]
        subgraph ROA["ROA Wrapper - LangChainROAWrapper"]
            subgraph LC["LangChain Agent"]
                AGENT["`create_agent or prompt fallback<br/>ChatOllama reasoning`"]
                TOOL["`Submit_Policy_Proposal<br/>action, resource_id, reason`"]
                AGENT -->|JSON Claim| TOOL
            end
        end
        TOOL -->|intercepted| WALL
    end

    WALL{{"`THE WALL<br/>Claim to PolicyProposal`"}}

    subgraph KS["KERNEL SPACE - Deterministic - DIR"]
        DIM["`validate_finops_proposal()<br/>L1: Schema + RBAC<br/>L2: Resource in Context Store<br/>L3: Environment in allowed_environments`"]
        ACCEPT["ACCEPT"]
        REJ["REJECT"]
        DIM --> ACCEPT & REJ
    end

    WALL --> DIM
    CTXSTORE -.->|instance env| DIM
    CONTRACT -.->|boundaries| DIM
    LLMCFG -.->|model / endpoint| LC

    style US fill:#fffde7,stroke:#f9a825,color:#333
    style KS fill:#e8f5e9,stroke:#388e3c,color:#333
    style ROA fill:#fff9c4,stroke:#f57f17,color:#333
    style LC fill:#fff3e0,stroke:#e65100,color:#333
    style WALL fill:#37474f,color:#fff
    style ACCEPT fill:#c8e6c9,stroke:#2e7d32,color:#1b5e20
    style REJ fill:#ffcdd2,stroke:#c62828,color:#b71c1c
```

### Diagram 2: Execution Flow. End-to-end sequence for a single scenario

```mermaid
sequenceDiagram
    actor Caller as run.py
    participant CFG as config.yaml
    participant Wrapper as LangChainROAWrapper
    participant LLM as ChatOllama (Gemma3)
    participant DIM as DIM Validator (Kernel Space)
    participant CS as Context Store (config.yaml)

    Caller ->> CFG: load_config()
    CFG -->> Wrapper: AppConfig(contract, llm, context_store, scenarios)

    loop for each scenario in config.yaml (3 scenarios: A, B, C)
        Caller ->> Wrapper: run(dfid, idle_resources)

        rect rgb(255, 253, 231)
            Note over Wrapper, LLM: USER SPACE - probabilistic

            Wrapper ->> LLM: idle instances + mission prompt
            alt model supports tools
                LLM -->> Wrapper: tool call Submit_Policy_Proposal
            else model does not support tools (gemma3)
                LLM -->> Wrapper: JSON in text response
            end
            Wrapper -->> Wrapper: PolicyProposal from JSON
        end

        Note over Wrapper, DIM: THE WALL - Claim to PolicyProposal

        rect rgb(232, 245, 233)
            Note over DIM, CS: KERNEL SPACE - deterministic

            Wrapper ->> DIM: validate_finops_proposal(proposal, context_store, contract)
            DIM ->> CS: lookup instance (environment)
            CS -->> DIM: instance record

            alt L1-L3 pass, env in [DEV, STG]
                DIM -->> Caller: ACCEPT
            else L3 fail: instance is PROD
                DIM -->> Caller: REJECT (environment boundary)
            end
        end
    end
```

### Diagram 3: Test Scenarios. 3 scenarios through the DIM validation pipeline

```mermaid
---
config:
  layout: elk
---
flowchart TD
    subgraph SCENARIOS["config.yaml - scenarios"]
        SA["`A - idle_resources<br/>i-prod-api-01 (72h) + i-dev-worker-03 (48h)`"]
        SB["`B - idle_resources<br/>i-dev-worker-03 (48h) only`"]
        SC["`C - idle_resources<br/>i-prod-api-01 (72h) env=DEV wrong`"]
    end

    subgraph AGENT_US["LangChain Agent - User Space - ChatOllama"]
        PROP["`create_agent or prompt fallback<br/>output: TERMINATE proposal JSON`"]
    end

    SA & SB & SC --> PROP

    WALL{{"THE WALL"}}
    PROP --> WALL

    subgraph DIM_KS["DIM - Kernel Space - validate_finops_proposal"]
        L1["L1 Schema + RBAC - pass"]
        L2["L2 Resource in Context Store - pass"]
        L3{"`L3 Instance environment<br/>in allowed [DEV, STG]?`"}
    end

    WALL --> L1 --> L2 --> L3

    L3 -->|i-dev-worker-03 is DEV - A, B| RA
    L3 -->|i-prod-api-01 is PROD - C| RC

    RA["`**ACCEPT**<br/>A, B`"]
    RC["`**REJECT**<br/>C - PROD not allowed`"]

    style SCENARIOS fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    style AGENT_US fill:#fffde7,stroke:#f9a825,color:#333
    style DIM_KS fill:#e8f5e9,stroke:#388e3c,color:#333
    style WALL fill:#37474f,color:#fff
    style RA fill:#c8e6c9,stroke:#2e7d32,color:#1b5e20
    style RC fill:#ffcdd2,stroke:#c62828,color:#b71c1c
```

### Key Difference from a Naive Agent

| | Naked LangChain Agent | ROA-Wrapped Agent |
|---|---|---|
| Actions | Any tool, any API, any DB | Only Submit_Policy_Proposal (or prompt JSON) |
| Enforcement | None (trust the LLM) | Deterministic DIM in Kernel Space |
| Output | Side effects (Facts) | Proposals (Claims) |
| Authority | Unbounded | FinOpsContract boundaries |

---

## The FinOps Scenario

### Agent vs DIM: Who Validates What?

The **LangChain agent** (LLM) receives only the **idle_resources** from the scenario. It has no access to Context Store. It can infer environment from instance id (prod/dev/stg) or trust input labels when `trust_input_labels=true`. The **DIM** (Kernel Space) is the source of truth: it reads `environment` from Context Store and enforces rules deterministically. If the agent proposes PROD (e.g. due to mislabeled input), DIM rejects. This separation is intentional: User Space proposes, Kernel Space decides.

### Mission

Analyze cloud usage logs and reduce costs by shutting down idle resources, without disrupting production.

### Responsibility Contract (FinOpsContract)

| Field | Description |
|-------|-------------|
| `allowed_environments` | Instance environments agent may propose actions on (DEV, STG; PROD prohibited) |
| `allowed_policy_types` | Actions agent may propose (TERMINATE, STOP, SCALE_DOWN) |

### Context Store (config.yaml)

Authoritative infrastructure state. DIM validates against it; the agent never sees it directly.

```yaml
context_store:
  instances:
    i-prod-api-01:
      environment: PROD
      idle_hours: 72
      name: prod-api-01
    i-dev-worker-03:
      environment: DEV
      idle_hours: 48
      name: dev-worker-03
```

### Test Scenarios

| Scenario | Input (idle_resources) | Agent sees | DIM Verdict | Reason |
|----------|------------------------|------------|-------------|--------|
| **A** | i-prod-api-01 (72h) + i-dev-worker-03 (48h) | Both; infers env from id | ACCEPT | Agent chooses DEV; i-dev-worker-03 is DEV |
| **B** | i-dev-worker-03 (48h) only | DEV only | ACCEPT | Single option within bounds |
| **C** | i-prod-api-01 (72h) with env=DEV (wrong) | Trusts input label | REJECT | DIM: instance is PROD in Context Store |

---

## How the Wrapper Works

### Tool Injection

The agent has exactly one "action" tool: `Submit_Policy_Proposal`. All other tools (real AWS API calls, database writes, etc.) are **removed or replaced**. The agent cannot execute side effects directly. It can only propose.

### Interception

When the agent invokes `Submit_Policy_Proposal` with a JSON payload (e.g. `{"action": "TERMINATE", "resource_id": "i-0123456789"}`), the wrapper:

1. **Catches** the invocation before any real execution
2. **Parses** the JSON into structured fields
3. **Constructs** a DIR `PolicyProposal` with `dfid`, `agent_id`, `policy_kind`, `params`
4. **Halts** the LangChain loop; no further tool calls
5. **Returns** the proposal to the caller

The tool raises a custom exception (`ProposalIntercepted`) that the wrapper catches. This ensures the agent's "execution" is intercepted and never reaches external systems.

### Claim vs. Fact

A `PolicyProposal` is a **Claim**, an untrusted assertion. The agent *claims* that terminating instance `i-0123456789` is the right move. It becomes a **Fact** (an executed event) only after:

1. The DIM validates schema, RBAC, and state consistency
2. The Execution Engine creates an `ExecutionIntent`
3. The side effect is performed with idempotency guarantees

This distinction prevents "authority bias": we do not implicitly trust the AI because it produced an output (DIR §5.3).

---

## Production Considerations

This sample uses a **real LangChain agent + LLM (Ollama)** with `create_agent` (LangGraph-based). Models that don't support tools (e.g. gemma3) use a prompt-based JSON fallback automatically. The following aspects are simplified for the demo:

### What This Sample Demonstrates

| Aspect | Sample Implementation | Production Requirement |
|--------|----------------------|------------------------|
| **Agent reasoning** | Real LLM (ChatOllama) via create_agent or prompt fallback | Same: LangChain + LLM |
| **Tool invocation** | create_agent (LangGraph) or prompt-based JSON when model lacks tool support | Tool mode when supported |
| **Concurrency** | Single-threaded, synchronous | Async execution, thread-safe state |
| **State management** | Context Store from config.yaml | Persistent Context Store (DB/cache) |
| **Error handling** | Basic exception flow | Retry logic, circuit breakers, dead-letter queues |

### Production Integration Pattern

```python
# Production wrapper: same pattern as this sample
from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

class ProductionROAWrapper:
    def __init__(self, contract: FinOpsContract, llm_cfg: LlmConfig):
        self.contract = contract
        self.llm = ChatOllama(model=llm_cfg.model, base_url=llm_cfg.base_url)

        @tool
        def submit_policy_proposal(proposal_json: str) -> str:
            """Submit proposal to DIR Kernel."""
            raise ProposalIntercepted(proposal_json)

        self.graph = create_agent(
            model=self.llm,
            tools=[submit_policy_proposal],
            system_prompt=self._build_system_prompt(),
        )

    def run(self, dfid: str, context: str) -> PolicyProposal:
        try:
            self.graph.invoke({"messages": [HumanMessage(content=context)]})
        except ProposalIntercepted as e:
            return self._convert_to_proposal(dfid, e.proposal_json)
        # Fallback: if model doesn't support tools, use prompt-based JSON (see run.py)
```

### Additional Production Requirements

1. **Multi-proposal handling**: Real agents may propose multiple actions in one session. Production systems need proposal batching or iterative validation.

2. **Timeout and cancellation**: LLM calls can hang. Implement timeouts and graceful cancellation.

3. **Audit trail**: Log every proposal with DFID, timestamp, raw LLM output, and DIM verdict for compliance.

4. **Cost controls**: LLM API costs can spike. Implement rate limiting and budget caps per agent.

5. **Rollback mechanisms**: If execution fails after DIM ACCEPT, system needs compensating transactions.

6. **Human-in-the-loop**: For high-risk proposals (e.g., PROD actions), add approval workflow before execution.

---

## Configuration

All agent configuration lives in **`config.yaml`**. Same convention as `samples/35_crewai_roa_wrapper/config.yaml`.

```yaml
llm_defaults:
  model: "gemma3:4b"
  base_url: "http://localhost:11434"
  temperature: 0.2

agent:
  agent_id: "finops_autoscaler_v1"
  mission: "Analyze cloud usage logs and reduce costs..."
  contract:
    role: EXECUTOR
    allowed_environments: [DEV, STG]
    allowed_policy_types: [TERMINATE, STOP, SCALE_DOWN]

context_store:
  instances:
    i-prod-api-01: { environment: PROD, idle_hours: 72, name: prod-api-01 }
    i-dev-worker-03: { environment: DEV, idle_hours: 48, name: dev-worker-03 }

scenarios:
  - label: "SCENARIO A - Agent sees PROD + DEV..."
    idle_resources:
      instances:
        - { id: i-prod-api-01, idle_hours: 72 }
        - { id: i-dev-worker-03, idle_hours: 48 }
    expected: ACCEPT
    show_mission_demo: true

  - label: "SCENARIO B - Agent sees only DEV..."
    idle_resources:
      instances:
        - { id: i-dev-worker-03, idle_hours: 48 }
    expected: ACCEPT

  - label: "SCENARIO C - Mislabeled data (PROD tagged as DEV)..."
    idle_resources:
      instances:
        - { id: i-prod-api-01, idle_hours: 72, environment: DEV }
    expected: REJECT
    trust_input_labels: true
```

| Section | Purpose |
|---------|---------|
| `llm_defaults` | LLM model and Ollama endpoint |
| `agent.contract` | Responsibility Contract: allowed_environments, allowed_policy_types |
| `context_store` | Authoritative instance data (source of truth for DIM, invisible to agent) |
| `scenarios` | Test cases: `idle_resources` (what agent sees), `expected` verdict |

---

## How to Run

Running `run.py` loads `config.yaml` and executes **all 3 scenarios** (A, B, C) in sequence. Each scenario runs: idle_resources → LangChain agent → DIM validation. The final summary reports verdict per scenario.

```bash
# 1. Install dependencies (from repo root)
pip install -e .
pip install -r samples/34_langchain_roa_wrapper/requirements.txt

# 2. Start Ollama and pull the model (configured in config.yaml)
ollama serve
ollama pull gemma3:4b

# 3. Run (from repo root)
python samples/34_langchain_roa_wrapper/run.py
```

**No cloud API key needed**; uses local Ollama (same as `samples/35_crewai_roa_wrapper`).

**Env var overrides** (same convention as sample 35):
```bash
# PowerShell
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_MODEL    = "gemma3:4b"

# cmd
set OLLAMA_BASE_URL=http://localhost:11434
set OLLAMA_MODEL=gemma3:4b
```

---

## Expected Output

```
======================================================================
34_langchain_roa_wrapper - LangChain ROA Wrapper / FinOps Demo
======================================================================

[SCENARIO A - Agent sees PROD + DEV, proposes TERMINATE on most-idle (PROD)]
----------------------------------------------------------------------

======================================================================
[MISSION INJECTION DEMO]
======================================================================

🔴 NAKED LangChain Agent: 'terminate the most expensive ones', no boundaries
🟢 ROA-WRAPPED: Mission + allowed_environments=[DEV, STG], PROD prohibited
======================================================================

  [REQUEST] Agent input (idle instances):
    - i-prod-api-01: idle_hours=72, env=(infer from id)
    - i-dev-worker-03: idle_hours=48, env=(infer from id)

  [MODE] Prompt-based JSON (model does not support tools)

  [LANGCHAIN OUTPUT] Agent proposal:
    action: TERMINATE
    resource_id: i-dev-worker-03
    reason: Idle 48h, within allowed environments

  [DIM VERDICT] ACCEPT
    WHY ACCEPTED: i-dev-worker-03 is DEV, within allowed ['DEV', 'STG']
  -> Mission-aware agent autonomously avoided PROD, selected DEV instead.

[SCENARIO B - Agent sees only DEV, proposes TERMINATE]
----------------------------------------------------------------------

  [REQUEST] Agent input (idle instances):
    - i-dev-worker-03: idle_hours=48, env=(infer from id)

  [LANGCHAIN OUTPUT] Agent proposal:
    action: TERMINATE
    resource_id: i-dev-worker-03
    reason: ...

  [DIM VERDICT] ACCEPT
    WHY ACCEPTED: i-dev-worker-03 is DEV, within allowed ['DEV', 'STG']
  -> Safe to execute (within allowed_environments).

[SCENARIO C - Mislabeled data (PROD tagged as DEV), DIM REJECT]
----------------------------------------------------------------------

  [REQUEST] Agent input (idle instances):
    - i-prod-api-01: idle_hours=72, env=DEV

  [LANGCHAIN OUTPUT] Agent proposal:
    action: TERMINATE
    resource_id: i-prod-api-01
    reason: ...

  [DIM VERDICT] REJECT
    WHY REJECTED: Instance i-prod-api-01 is PROD; agent allowed_environments=['DEV', 'STG']
  -> DIM rejected PROD termination (defense-in-depth).

======================================================================
[SUMMARY] LangChain ROA Wrapper - FinOps Demo
======================================================================
  SCENARIO A - Agent sees PROD + DEV, proposes TERMI...
    -> DIM verdict: ACCEPT (resource: i-dev-worker-03)
  SCENARIO B - Agent sees only DEV, proposes TERMINA...
    -> DIM verdict: ACCEPT (resource: i-dev-worker-03)
  SCENARIO C - Mislabeled data (PROD tagged as DEV)...
    -> DIM verdict: REJECT (resource: i-prod-api-01)

  KEY INSIGHT: Mission injection transforms agent behavior BEFORE DIM.
  ...
======================================================================
```

**Output sections:**
- **[REQUEST]**: What the agent sees (idle instances from scenario)
- **[LANGCHAIN OUTPUT]**: What the agent proposed (action, resource_id, reason)
- **[DIM VERDICT]**: ACCEPT or REJECT with explicit reason (WHY ACCEPTED / WHY REJECTED)

**Note:** Models like gemma3 don't support tools; the sample uses prompt-based JSON fallback (`[MODE] Prompt-based JSON`). Models with tool support (e.g. llama3.1) use `create_agent` with Submit_Policy_Proposal tool.

---

## Key Components

| Component | Purpose |
|-----------|---------|
| `config.yaml` | LLM (llm_defaults), agent contract, context store, test scenarios (same structure as 35_crewai_roa_wrapper) |
| `config_loader.py` | Loads config.yaml, builds LlmConfig, FinOpsContract, ScenarioConfig |
| `contracts.py` | FinOpsContract with `allowed_environments`, `from_config()` |
| `LangChainROAWrapper` | Real LangChain agent (create_agent) + ChatOllama; mission injection; tool or prompt fallback |
| `Submit_Policy_Proposal` | Tool that raises `ProposalIntercepted`; wrapper catches and converts to `PolicyProposal` |
| `validate_finops_proposal()` | DIM logic: schema + RBAC + resource existence + environment boundary |
| Context Store | From config: authoritative instance env (PROD/DEV/STG); DIM validates against it |

---

## References

- [ROA Manifesto](../../docs/01-roa-manifesto/ROA_Manifesto.md) §3 (Responsibility Contract), §4-5 (Explain → Policy → Proposal)
- [DIR Architectural Pattern](../../docs/02-decision-runtime/DIR_Architectural_Pattern.md) §6 (Decision Integrity Module), §5 (Policies as Contracts)
- [Sample 35 - CrewAI ROA Wrapper](../35_crewai_roa_wrapper/README.md) (same pattern, different framework)
