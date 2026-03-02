# 35 - CrewAI ROA Wrapper

**Goal:** Demonstrate that **Task-Oriented Agents (CrewAI) and Mission-Oriented Agents (ROA) can coexist**. Wrap a real CrewAI Crew in an ROA interface, producing structured JSON output (`output_json`) and converting it to DIR `PolicyProposal` (Claim) instead of direct execution (Fact). Prove the pattern with a **Customer Claims Agent** use case where the DIR Kernel rejects/escalates refund proposals based on return window, amount limits, and category boundaries.

**DIR Alignment:** ROA Manifesto §4-5 (Explain → Policy → Proposal; User Space vs. Kernel Space), §10 (Boxed Intelligence), DIR Architectural Pattern §6 (Decision Integrity Module)

---

## The Core Concept: Taming the Task-Oriented Crew

CrewAI Crews are **collaborative, task-driven agents** (e.g., Analyst + Decision Maker). They receive inputs, reason, call tools, and execute. They have no mission, no boundaries, no persistent responsibility. They are optimized for *"What can the crew do next?"*-not *"What is this crew responsible for?"* (ROA Manifesto §3).

This creates a fundamental mismatch. In production, Crews:

- Execute side effects directly (API calls, database writes)
- Lack authority boundaries (they may act outside their intended scope)
- Provide no deterministic safety guarantees

**The solution:** Wrap the Crew in an ROA shell. The Crew retains its reasoning power but is **forced** to output via structured JSON (`output_json` / `RefundProposalOutput`). That output does not execute. It passes intent over "The Wall" to the DIR Kernel Space.

The result: a mission-oriented Crew whose outputs are **Claims**, not **Facts**. A Claim becomes a Fact only after the Decision Integrity Module validates it and the Execution Engine runs it (DIR §6-7).

---

## Architecture

### Diagram 1 - System Overview: CrewAI wrapped by ROA, processed by DIR

```mermaid
---
config:
  layout: elk
---
flowchart TB
    subgraph CFG["config.yaml"]
        LLMCFG["`llm_defaults<br/>gemma3:4b @ localhost:11435`"]
        CONTRACT["`agent.contract - ClaimsContract<br/>allowed_categories - max_refund - return_window`"]
        CTXSTORE["`context_store - Orders<br/>purchase_date - category - amount`"]
    end

    subgraph US["USER SPACE - Probabilistic - Ollama / Gemma3"]
        subgraph ROA["ROA Wrapper - CrewAIROAWrapper"]
            subgraph CREW["CrewAI Crew - sequential"]
                ANA["`Claims Analyst<br/>LLM text reasoning`"]
                DM["`Decision Maker<br/>output_json = RefundProposalOutput`"]
                ANA -->|eligibility summary| DM
            end
        end
        DM -->|JSON Claim| WALL
    end

    WALL{{"`THE WALL<br/>Claim to PolicyProposal`"}}

    subgraph KS["KERNEL SPACE - Deterministic - DIR"]
        DIM["`validate_claims_proposal()<br/>L1: Schema + RBAC<br/>L2: Order existence<br/>L3: Category boundary<br/>L4: Return window<br/>L5: Amount limit`"]
        ACCEPT["ACCEPT"]
        ESC["`ESCALATE<br/>human review`"]
        REJ["REJECT"]
        DIM --> ACCEPT & ESC & REJ
    end

    WALL --> DIM
    CTXSTORE -.->|order data| DIM
    CONTRACT -.->|boundaries| DIM
    LLMCFG -.->|model / endpoint| CREW

    style US fill:#fffde7,stroke:#f9a825,color:#333
    style KS fill:#e8f5e9,stroke:#388e3c,color:#333
    style ROA fill:#fff9c4,stroke:#f57f17,color:#333
    style CREW fill:#fff3e0,stroke:#e65100,color:#333
    style WALL fill:#37474f,color:#fff
    style ACCEPT fill:#c8e6c9,stroke:#2e7d32,color:#1b5e20
    style ESC fill:#fff9c4,stroke:#f57f17,color:#e65100
    style REJ fill:#ffcdd2,stroke:#c62828,color:#b71c1c
```

### Diagram 2 - Execution Flow: end-to-end sequence for a single claim

```mermaid
sequenceDiagram
    actor Caller as run.py
    participant CFG as config.yaml
    participant Wrapper as CrewAIROAWrapper
    participant Analyst as Claims Analyst (CrewAI / Gemma3)
    participant DM as Decision Maker (CrewAI / Gemma3)
    participant DIM as DIM Validator (Kernel Space)
    participant CS as Context Store (config.yaml)

    Caller ->> CFG: load_config()
    CFG -->> Wrapper: AppConfig(contract, llm, context_store, scenarios)

    loop for each scenario in config.yaml (6 scenarios: A-F)
        Note over Caller, Wrapper: For E, F: extract_claim_from_text() runs first, then claim → run()
        Caller ->> Wrapper: run(dfid, claim)

        rect rgb(255, 253, 231)
            Note over Wrapper, DM: USER SPACE - probabilistic

            Wrapper ->> Analyst: Task: analyze claim eligibility
            Analyst ->> Analyst: Gemma3 reasoning
            Analyst -->> DM: eligibility summary (text)

            DM ->> DM: Gemma3 reasoning (output_json)
            DM -->> Wrapper: RefundProposalOutput JSON
        end

        Note over Wrapper, DIM: THE WALL - Claim to PolicyProposal

        rect rgb(232, 245, 233)
            Note over DIM, CS: KERNEL SPACE - deterministic

            Wrapper ->> DIM: validate_claims_proposal(proposal, context_store, contract)
            DIM ->> CS: lookup order (purchase_date, category)
            CS -->> DIM: order record

            alt L1-L4 pass AND amount <= 500 EUR
                DIM -->> Caller: ACCEPT
            else L1-L4 pass AND amount > 500 EUR
                DIM -->> Caller: ESCALATE
            else L2 fail - order not found
                DIM -->> Caller: REJECT (order unknown)
            else L3 fail - prohibited category
                DIM -->> Caller: REJECT (category boundary)
            else L4 fail - outside return window
                DIM -->> Caller: REJECT (return window)
            end
        end
    end
```

### Diagram 3 - Test Scenarios: 6 claims through the DIM validation pipeline

```mermaid
---
config:
  layout: elk
---
flowchart TD
    subgraph SCENARIOS["config.yaml - scenarios"]
        SA["`A - claim dict<br/>ord_001 - 299.99 EUR`"]
        SB["`B - claim dict<br/>ord_002 - 1200 EUR`"]
        SC["`C - claim dict<br/>ord_005 - 500 EUR`"]
        SD["`D - claim dict<br/>ord_004 - 50 EUR`"]
        SE["`E - claim_text NL<br/>ord_001 - 299.99 EUR`"]
        SF["`F - claim_text NL<br/>ord_002 - 1200 EUR`"]
    end

    subgraph EXTRACT["NL intake (E, F only)"]
        EX["`extract_claim_from_text()<br/>LLM → structured claim`"]
    end

    subgraph CREW_US["CrewAI Crew - User Space - Gemma3"]
        PROP["`Analyst to Decision Maker<br/>output: REFUND proposal JSON`"]
    end

    SA & SB & SC & SD --> PROP
    SE & SF --> EX
    EX --> PROP

    WALL{{"THE WALL"}}
    PROP --> WALL

    subgraph DIM_KS["DIM - Kernel Space - validate_claims_proposal"]
        L1["L1 Schema + RBAC - pass"]
        L2["L2 Order exists - pass"]
        L3{"`L3 Category<br/>in allowed list?`"}
        L4{"`L4 Purchase date<br/>within 14 days?`"}
        L5{"`L5 Amount<br/>max 500 EUR?`"}
    end

    WALL --> L1 --> L2 --> L3

    L3 -->|electronics / clothing / home| L4
    L3 -->|prohibited_category - D| RD

    L4 -->|within window - A, B, E, F| L5
    L4 -->|2026-01-01 expired - C| RC

    L5 -->|299.99 - A, E| RA
    L5 -->|1200.00 - B, F| RB

    RA["`**ACCEPT**<br/>A, E`"]
    RB["`**ESCALATE**<br/>B, F - human review`"]
    RC["`**REJECT**<br/>C - return window expired`"]
    RD["`**REJECT**<br/>D - category not allowed`"]

    style SCENARIOS fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    style EXTRACT fill:#e1f5fe,stroke:#0288d1,color:#01579b
    style CREW_US fill:#fffde7,stroke:#f9a825,color:#333
    style DIM_KS fill:#e8f5e9,stroke:#388e3c,color:#333
    style WALL fill:#37474f,color:#fff
    style RA fill:#c8e6c9,stroke:#2e7d32,color:#1b5e20
    style RB fill:#fff9c4,stroke:#f57f17,color:#e65100
    style RC fill:#ffcdd2,stroke:#c62828,color:#b71c1c
    style RD fill:#ffcdd2,stroke:#c62828,color:#b71c1c
```

### Key Difference from a Naive Crew

| | Naked CrewAI Crew | ROA-Wrapped Crew |
|---|---|---|
| Actions | Any tool, any API, any DB | Only structured JSON (`output_json`) |
| Enforcement | None (trust the LLM) | Deterministic DIM in Kernel Space |
| Output | Side effects (Facts) | Proposals (Claims) |
| Authority | Unbounded | `ClaimsContract` boundaries |

---

## The Claims Agent Scenario

### Analyst vs DIM - Who Validates What?

The **Claims Analyst** (LLM) analyzes only the **claim data** provided in the scenario - it has no access to Context Store. It can reason about boundaries (categories, limits) from the prompt text, but it may err (e.g., wrong return-window assessment). The **DIM** (Kernel Space) is the source of truth: it reads `purchase_date` and `category` from Context Store and enforces rules deterministically. If the Analyst says "OK" but the data contradicts - DIM rejects. This separation is intentional: User Space proposes, Kernel Space decides.

### Mission

Process customer claims fairly, within policy boundaries, without exceeding authority or escalating unnecessarily.

### Responsibility Contract (ClaimsContract)

| Field | Description |
|-------|-------------|
| `allowed_refund_categories` | Product categories agent may propose refunds for (e.g., electronics, clothing) |
| `max_refund_without_escalation` | EUR threshold-above requires human approval (ESCALATE) |
| `return_window_days` | Max days from purchase for automatic eligibility |

### Natural Language Intake (Scenarios E, F)

In production, customers write free-form text in English (e.g. *"I bought ord_001 for 299 EUR, defective product"*), not JSON. The LLM **extracts** structured claim data (`order_id`, `amount_eur`, `category`, `reason`) in a single call before the Crew processes it. This justifies the LLM: deterministic rules alone cannot parse natural language.

### Scenarios

| Scenario | Input | DIM Verdict | Reason |
|----------|-------|-------------|--------|
| **A** | Valid claim: within return window, amount ≤ 500 EUR | ACCEPT | All criteria met |
| **B** | Valid claim: amount > 500 EUR | ESCALATE | Human approval required |
| **C** | Claim outside return window (purchased 2026-01-01) | REJECT | Outside return_window_days |
| **D** | Claim for prohibited category | REJECT | Category not in allowed_refund_categories |
| **E** | NL text: valid claim (ord_001, 299.99 EUR) | ACCEPT | LLM extracts → DIM validates |
| **F** | NL text: amount > 500 EUR (ord_002, 1200 EUR) | ESCALATE | LLM extracts → DIM escalates |

---

## Configuration

All agent configuration lives in **`config.yaml`** - no hardcoded values in code.
Same convention as `samples/31_finance_trading/config.yaml`.

```yaml
llm_defaults:
  model: "gemma3:4b"
  base_url: "http://localhost:11435"
  temperature: 0.2

agent:
  agent_id: "claims_agent_v1"
  mission: "Process customer claims fairly, within policy boundaries..."
  contract:
    role: EXECUTOR
    allowed_refund_categories: [electronics, clothing, home]
    max_refund_without_escalation: 500.0   # EUR
    return_window_days: 14
    allowed_policy_types: [REFUND, REPLACE, ESCALATE]

context_store:
  orders:
    ord_001: { purchase_date: "2026-02-20T10:00:00Z", category: electronics, amount: 299.99 }
    ...

scenarios:
  - label: "SCENARIO A - Valid: within window & limit"
    claim: { order_id: ord_001, amount_eur: 299.99, ... }
    expected: ACCEPT

  - label: "SCENARIO E - NL intake: valid claim"
    claim_text: "I bought ord_001 for 299.99 EUR, defective product..."
    expected: ACCEPT
```

| Section | Purpose |
|---------|---------|
| `llm_defaults` | LLM model and Ollama endpoint |
| `agent.contract` | Responsibility Contract - authority boundaries enforced by DIM |
| `context_store` | Authoritative order data - source of truth for DIM, invisible to LLM |
| `scenarios` | Test cases: `claim` (dict) or `claim_text` (natural language: LLM extracts first) |

## How to Run

Running `run.py` loads `config.yaml` and executes **all 6 scenarios** (A–F) in sequence. Each scenario is run through: claim (or claim_text → extraction) → Crew → DIM validation. The final summary reports ✓/✗ per scenario against the expected verdict.

```bash
# 1. Install dependencies (from repo root)
pip install -e ".[crewai]"

# 2. Start Ollama and pull the model (configured in config.yaml)
ollama serve
ollama pull gemma3:4b

# 3. Run (from repo root)
python samples/35_crewai_roa_wrapper/run.py
```

**No cloud API key needed** - uses local Ollama (same as `samples/31_finance_trading`).

**Env var overrides** (same convention as sample 31):
```bash
# PowerShell
$env:OLLAMA_BASE_URL = "http://localhost:11434"   # overrides llm_defaults.base_url
$env:OLLAMA_MODEL    = "llama3.2"                 # overrides llm_defaults.model

# cmd
set OLLAMA_BASE_URL=http://localhost:11434
set OLLAMA_MODEL=llama3.2
```

**Why `provider="openai"`?**
CrewAI's LLM class routes `provider="openai"` to the native OpenAI Python SDK.
Ollama exposes an OpenAI-compatible API at `/v1`, so no LiteLLM or extra dependencies needed:
```python
LLM(model="gemma3:4b", provider="openai",
    base_url="http://localhost:11435/v1", api_key="ollama")
```

---

## How the Interception Works (output_json instead of tool-calling)

Gemma3 (and most local Ollama models) **do not support OpenAI-style function calling**.
The original `Submit_Policy_Proposal` tool approach requires the model to call functions - Ollama returns HTTP 400 for such requests.

**Solution: `output_json` on the Decision Maker's Task.**

CrewAI's `output_json` parameter instructs the LLM to format its entire response as JSON matching a Pydantic schema, then validates and parses it automatically:

```python
class RefundProposalOutput(BaseModel):
    action: str       # always "REFUND"
    order_id: str
    amount_eur: float
    category: str
    reason: str

decide_task = Task(
    description="Based on the analyst's findings, produce a refund proposal...",
    output_json=RefundProposalOutput,  # ← no tool-calling needed
    agent=decision_maker,              # ← no tools=[] on the agent
)

result = crew.kickoff()
data = result.json_dict  # parsed + validated dict
proposal = PolicyProposal(..., params=data)
```

**Architecturally equivalent**: the LLM still produces a **Claim** (JSON proposal), which crosses "The Wall" to the DIM for deterministic validation before any **Fact** (execution) occurs. The boundary holds.

---

## Key Components

| Component | Purpose |
|-----------|---------|
| `ClaimsContract` | Defines authority boundaries (categories, amount limit, return window) |
| `extract_claim_from_text()` | **NL intake:** extracts structured claim from customer text (single LLM call) |
| `ClaimExtractionOutput` | Pydantic schema for NL extraction output |
| `RefundProposalOutput` | Pydantic schema for `output_json` - structured proposal from Decision Maker |
| `_extract_proposal_from_text()` | Fallback: parses JSON from raw LLM output when `output_json` parse fails |
| `CrewAIROAWrapper` | Builds Crew per call, runs `kickoff()`, extracts `PolicyProposal` from JSON |
| `validate_claims_proposal()` | 5-layer DIM: schema → RBAC → order → category → return window → amount |
| Context Store | Authoritative order data (source of truth for DIM, not for the agent) |

---

## Expected Output

```
======================================================================
35_crewai_roa_wrapper  -  CrewAI + Ollama + DIR Kernel
======================================================================
  Config : config.yaml
  LLM    : gemma3:4b @ http://localhost:11435
  Agent  : claims_agent_v1
  Crew   : Claims Analyst → Decision Maker (sequential, output_json)
  DIM    : 5-layer validation (RBAC, order, window, category, amount)
  Scenarios: 6

[SCENARIO A - Valid: within window & limit]
----------------------------------------------------------------------
  Claim:  order=ord_001  amount=299.99 EUR  cat=electronics
  Crew:   thinking... done.
  Proposal:   REFUND ord_001 299.99 EUR
  DIM Verdict: ACCEPT
  Reason:      Validation passed

[SCENARIO B - Amount > 500 EUR (human approval required)]
----------------------------------------------------------------------
  Claim:  order=ord_002  amount=1200.0 EUR  cat=electronics
  Crew:   thinking... done.
  Proposal:   REFUND ord_002 1200.0 EUR
  DIM Verdict: ESCALATE
  Reason:      Amount 1200.0 EUR exceeds max_refund_without_escalation (500.0 EUR)...

[SCENARIO C - Outside return window (purchased 2026-01-01)]
----------------------------------------------------------------------
  Claim:  order=ord_005  amount=500.0 EUR  cat=electronics
  Crew:   thinking... done.
  Proposal:   REFUND ord_005 500.0 EUR
  DIM Verdict: REJECT
  Reason:      Order ord_005 outside return window...

[SCENARIO D - Prohibited category]
----------------------------------------------------------------------
  Claim:  order=ord_004  amount=50.0 EUR  cat=prohibited_category
  Crew:   thinking... done.
  Proposal:   REFUND ord_004 50.0 EUR
  DIM Verdict: REJECT
  Reason:      Category 'prohibited_category' not in allowed_refund_categories...

[SCENARIO E - NL intake: valid claim (ord_001)]
----------------------------------------------------------------------
  Input (NL): I bought electronics order ord_001 for 299.99 EUR on 20 February 2026...
  Extracted: order=ord_001  amount=299.99 EUR  cat=electronics
  Crew:   thinking... done.
  Proposal:   REFUND ord_001 299.99 EUR
  DIM Verdict: ACCEPT
  Reason:      Validation passed

[SCENARIO F - NL intake: amount > 500 EUR (ord_002)]
----------------------------------------------------------------------
  Input (NL): Order ord_002 - laptop for 1200 EUR, 25 February 2026...
  Extracted: order=ord_002  amount=1200.0 EUR  cat=electronics
  Crew:   thinking... done.
  Proposal:   REFUND ord_002 1200.0 EUR
  DIM Verdict: ESCALATE
  Reason:      Amount 1200.0 EUR exceeds max_refund_without_escalation (500.0 EUR)...

======================================================================
[SUMMARY]
======================================================================
  ✓ ACCEPT      SCENARIO A - Valid: within window & limit
  ✓ ESCALATE    SCENARIO B - Amount > 500 EUR (human approval required)
  ✓ REJECT      SCENARIO C - Outside return window (purchased 2026-01-01)
  ✓ REJECT      SCENARIO D - Prohibited category
  ✓ ACCEPT      SCENARIO E - NL intake: valid claim (ord_001)
  ✓ ESCALATE    SCENARIO F - NL intake: amount > 500 EUR (ord_002)
```

---

## References

- [ROA Manifesto](../../docs/01-roa-manifesto/ROA_Manifesto.md) §3 (Responsibility Contract), §4-5 (Explain → Policy → Proposal), §10 (Boxed Intelligence)
- [DIR Architectural Pattern](../../docs/02-decision-runtime/DIR_Architectural_Pattern.md) §6 (Decision Integrity Module), §5 (Policies as Contracts)
- [Sample 34 - LangChain ROA Wrapper](../34_langchain_roa_wrapper/README.md) (same pattern, different framework)
