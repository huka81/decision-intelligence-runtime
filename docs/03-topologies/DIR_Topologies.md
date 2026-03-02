<sup> Author: Artur Huk | [GitHub](https://github.com/huka81/decision-intelligence-runtime) | Created: 2026-01-15 | Last updated: 2026-02-20 </sup>

---

# Decision Intelligence Topologies: Scaling Auditable Autonomy
![Decision Intelligence Topologies](../../assets/images/3_topologies_scratch.png)

### Agent orchestration patterns for complex decision systems


## 0. Abstract

> **Disclaimer:** This document describes system topologies and communication patterns for autonomous agents. It assumes the existence of the **Decision Intelligence Runtime (DIR)** to handle deterministic execution and the **Responsibility-Oriented Agents (ROA)** framework to define agent identity.

The transition from experimental AI scripts to production-grade decision systems requires a fundamental shift in how agents interact within an environment. A single architectural pattern cannot satisfy the conflicting requirements of complex, multi-perspective strategic reasoning, high-frequency tactical execution, and absolute compliance verification.

This whitepaper introduces **Decision Intelligence Topologies**, a pluralistic approach to agent orchestration. We define three distinct operational modes:

1.  **Topology A: Event-Oriented Agent Mesh (EOAM)** - A decentralized pattern for "Organizational Choreography," where responsibility-bound agents collaborate through a reactive event substrate to form a "Digital Twin" of professional decision-making.
2.  **Topology B: Sovereign Decision Stream (SDS)** - A linear, high-velocity pattern for "Atomic Execution," leveraging **Constrained Decoding** to achieve **Syntactically Bound by Design** operations at machine speeds.
3.  **Topology C: Decision Ledger (DL+PCI)** - The pattern for "Formal Verification & Absolute Audit," focusing on the integrity of the intent artifact rather than the behavior of the agent.

By selecting the appropriate topology for the specific decision class, verified by **DecisionFlow IDs (DFID)** and governed by the **Decision Intelligence Runtime**, organizations can build systems that are scalable, auditable, and resilient to the non-deterministic nature of Large Language Models.

---

## 1. The Case for Architectural Pluralism

In the early phases of AI adoption, engineers often seek a "Universal Agent Architecture"-a single loop to rule them all. However, in production environments like the **AIvestor** financial system, this monolithic approach fails. The latency required to "think fast" (scalping a price inefficiency) is incompatible with the comprehensive context required to "think slow" (rebalancing a portfolio against geopolitical risk).

To solve this, we decouple the **Identity Layer** from the **Topology Layer**:

*   **The Identity Layer (ROA):** Who acts? (Defined by Mission, Authority, and Responsibility Contracts).
*   **The Execution Kernel (DIR):** How is it validated? (Defined by DFIDs, Hard Gates, and Idempotency).
*   **The Topology (EOAM / SDS / DL):** How do signals flow, and where does trust originate?

Each topology defines two orthogonal properties:

1.  **Signal Flow** — the communication pattern between agents and the runtime (mesh, stream, or ledger).
2.  **Trust Locus** — the architectural location where safety is guaranteed:
    *   **Process** (EOAM): The Runtime validates proposals *after* generation.
    *   **Generation** (SDS): The Grammar constrains output *during* inference.
    *   **Artifact** (DL+PCI): The Proof-Carrying Intent carries verifiable evidence *within itself*.

This separation allows a single systems architecture to support deliberate mesh networks, hyper-fast singular streams, and formally verified ledgers side-by-side. The three topologies are not incremental layers of the same pattern; they represent fundamentally different answers to the question: *"Where does safety come from?"*

A key motivation for this pluralistic approach is the limitation of conventional multi-agent frameworks, which typically rely on unstructured LLM-to-LLM dialogue or manager-led hierarchies. While powerful for creative synthesis, these patterns produce non-deterministic outcomes that are difficult to audit in regulated environments. The topologies defined here replace **dialogue with choreography** (typed signals, not chat), **democracy with priority** (deterministic preemption, not negotiation), and **mystery with audit** (DFID-bound causal chains, not opaque chat logs).

```mermaid
---
title: "Architectural Pluralism: Decoupling Identity from Topology"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart TB
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;
    classDef infraSpace fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold;

    subgraph Identity_Layer ["`**IDENTITY LAYER (ROA)**<br/>Who Acts?`"]
        Registry(["`**Agent Registry**<br/>Mission & Authority`"]):::kernelSpace
    end

    subgraph Topology_Selector ["`**TOPOLOGY LAYER**<br/>Signal Flow & Trust Locus`"]
        direction TB
        Selector{"`**Selector**`"}:::kernelSpace
        
        subgraph EOAM ["`**Topology A: EOAM**<br/>Mesh (Complex)`"]
            MeshAgents(["`**Collaborating Agents**<br/>Parallel Reasoning`"]):::userSpace
        end
        
        subgraph SDS ["`**Topology B: SDS**<br/>Stream (Fast)`"]
            StreamAgent(["`**Sovereign Agent**<br/>Atomic Execution`"]):::userSpace
        end

        subgraph DL ["`**Topology C: DL+PCI**<br/>Ledger (Verified)`"]
            LedgerAgent(["`**Prover Agent**<br/>Formal Verification`"]):::userSpace
        end
    end

    subgraph Execution_Kernel ["`**EXECUTION KERNEL (DIR)**<br/>How is it validated?`"]
        DIM{"`**DIM Gate**<br/>Validation`"}:::kernelSpace
        Engine["`**Execution Engine**<br/>Side Effects`"]:::infraSpace
    end

    Registry --> Selector
    Selector -->|Complex| EOAM
    Selector -->|Fast| SDS
    Selector -->|Audit| DL
    
    MeshAgents --> DIM
    StreamAgent --> DIM
    LedgerAgent --> DIM
    
    DIM --> Engine

    style Identity_Layer fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style Topology_Selector fill:#FAFAFA,stroke:#3F51B5,stroke-width:3px
    style Execution_Kernel fill:#FAFAFA,stroke:#F57C00,stroke-width:3px
```

---

## 2. Topology A: The Event-Oriented Agent Mesh (EOAM)

**Primary Attribute:** Organizational Choreography
**Ideal For:** Complex Strategy, Multi-Perspective Analysis, Resilience

EOAM is a decentralized architectural pattern where autonomous agents collaborate through a reactive event substrate. It defines a system that is **"Decentralized in activation, centralized in authority."** EOAM trades the conceptual simplicity of linear orchestration for the power of **parallelism** and **resilience**.

### 2.1 Scope-Based Choreography

EOAM replaces the central "Manager" with **Scope-Based Choreography**. Agents do not wait for commands; they are reactive entities that monitor the event bus for **Observations** or **Triggers** that fall within their defined **Responsibility Contract**.

*   **Autonomy through Subscription:** Agents subscribe to specific metadata-such as a ticker symbol or risk domain-defined in the **Agent Registry**.
*   **Decentralized Intelligence:** When a new signal (e.g., a news event) enters the mesh, all relevant agents (Risk, Sentiment, Strategy) are activated in parallel.
*   **Inversion of Control:** The Runtime does not "call" agents; it emits a context-rich event, and agents "claim" the responsibility to reason.

### 2.2 The Anatomy of a Mesh Event

Every event transmitted through the mesh adheres to a strict schema to facilitate causality tracking.

*   **DecisionFlow ID (DFID):** The primary correlation identifier, functioning as an immutable trace header for the entire decision lifecycle. It allows for narrative reconstruction and deterministic idempotency.
*   **ContextSnapshotID:** A unique hash representing the exact "frozen reality" that an agent utilized. This ensures that every **PolicyProposal** is linked to the version of the world the agent "saw," enabling **Just-In-Time (JIT) State Verification**.

### 2.3 Semantic Routing & Economic Guardrails

In a decentralized mesh, mitigating noise and cost is critical.

*   **Semantically Constrained Routing:** The underlying transport acts as a "dumb pipe," relying on rules from the **Agent Registry** to match topics to subscribers based on Least Privilege.
*   **Wake-up Predicates (Signal Suppression):** To prevent "Token Burn" (waking up expensive LLMs for minor signals), the Runtime evaluates low-cost heuristic predicates (e.g., `abs(price_delta) > 0.5%`) defined in the agent's manifest. If the predicate fails, the event is suppressed at the routing layer.
*   **Economic Admission Control:** The Mesh implements a strict "Budget-to-Signal" filter. The system determines how many agents to activate based on signal volatility and available token budget, preventing "Thundering Herd" costs where low-value signals trigger expensive multi-agent cascades.

### 2.4 The Mesh Decision Lifecycle

1.  **Observation:** A raw signal triggers a new **DecisionFlow**. The Runtime generates an authoritative **Context Snapshot** (cached to prevent **Read Contention** on the database).
2.  **Distributed Parallel Reasoning:** Agents reason in parallel, producing **PolicyProposals**.
3.  **Priority-Based Preemption Model:** The Runtime utilizes a priority-driven logic rather than a simple time window. It collects proposals and applies the **Agent Registry Priority Matrix** to select the winner. High-priority agents (e.g., Risk Monitors) can preempt or invalidate earlier strategic proposals, ensuring safety always overrides strategy.
4.  **JIT Verification:** The Runtime compares the live state against the `ContextSnapshotID`. If the **Drift** exceeds the agent-defined **Drift Envelope** (a contract-level parameter stored in the Registry), the execution is rejected. This prevents actions based on stale data (e.g., execution against a price that has moved beyond the allowable slippage/latency threshold).

```mermaid
---
title: "Topology A: EOAM Decision Lifecycle"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart LR
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;
    classDef infraSpace fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold;

    Trigger((Signal)) --> Context
    
    subgraph Kernel_Prep ["`**1. PREPARATION**`"]
        Context["`**Context Snapshot**<br/>Frozen Reality`"]:::kernelSpace
    end

    subgraph User_Reasoning ["`**2. PARALLEL REASONING (Mesh)**`"]
        direction TB
        Agent1(["`**Risk Agent**<br/>(High Priority)`"]):::userSpace
        Agent2(["`**Strategy Agent**<br/>(Low Priority)`"]):::userSpace
        
        Context --> Agent1
        Context --> Agent2
    end

    subgraph Kernel_Arbitration ["`**3. ARBITRATION & VALIDATION**`"]
        Arbitrator{"`**Priority Matrix**<br/>Preemption`"}:::kernelSpace
        JIT{"`**JIT Check**<br/>Drift Verification`"}:::kernelSpace
    end
    
    subgraph Execution ["`**4. ACTION**`"]
        Exec["`**Execution Intent**`"]:::infraSpace
    end

    Agent1 -->|Proposal A| Arbitrator
    Agent2 -->|Proposal B| Arbitrator
    
    Arbitrator -->|Winner Selected| JIT
    JIT -->|Pass| Exec

    style Kernel_Prep fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style User_Reasoning fill:#FAFAFA,stroke:#3F51B5,stroke-width:3px
    style Kernel_Arbitration fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style Execution fill:#FAFAFA,stroke:#F57C00,stroke-width:3px
```

### 2.5 Holistic EOAM Architecture (Example Implementation)

The following diagram illustrates a complete "Event-Oriented Agent Mesh" implementation, derived from the **AIvestor** reference system. It demonstrates how Data Sources, Agents, and Execution components map to the DIR architectural spaces (Infrastructure, User, Kernel).

```mermaid
---
config:
  layout: dagre
  theme: neutral
  look: classic
title: Holistic EOAM Architecture (AIvestor Reference)
---
flowchart LR
 subgraph Data_Sources["**Data Sources**"]
    direction TB
        MarketData["Market Data"]
        MacroData["Macro Data"]
        NewsData["ESPI News"]
  end
 subgraph Infrastructure_Layer["**INFRASTRUCTURE SPACE**<br>External Data &amp; Interfaces"]
    direction LR
        Data_Sources
        BrokerAPI["Broker API"]
        Dashboard["Web Dashboard"]
  end
 subgraph Kernel_Layer["**KERNEL SPACE (DIR)**<br>Runtime &amp; State"]
    direction TB
        Ingest["Scrapers & Scoring"]
        EventBus(("Event Bus"))
        Postgres[("Context Store")]
        Executor["Order Executor"]
        Safety["Safety Limits / DIM"]
  end
 subgraph User_Layer["**USER SPACE (AGENTS)**<br>Reasoning Mesh"]
    direction LR
        Scanner(["Market Scanner"])
        NewsAgent(["News Opportunity"])
        Portfolio(["Portfolio Manager"])
        InstAgents(["Instrument Agents 1..N"])
  end
    MarketData --> Ingest
    MacroData --> Ingest
    NewsData --> Ingest
    Ingest --> Postgres & EventBus
    EventBus <--> Scanner & NewsAgent & Portfolio & InstAgents
    Scanner -- Proposals --> Safety
    NewsAgent -- Proposals --> Safety
    Portfolio -- Proposals --> Safety
    InstAgents -- Proposals --> Safety
    Safety -- Validated Intent --> Executor
    Executor -- Execute --> BrokerAPI
    BrokerAPI -- Confirmation --> EventBus
    Dashboard <--> EventBus
    Dashboard -. Config .-> Safety
    Dashboard -. Modes .-> Portfolio

     MarketData:::infraSpace
     MacroData:::infraSpace
     NewsData:::infraSpace
     BrokerAPI:::infraSpace
     Dashboard:::infraSpace
     Ingest:::kernelSpace
     EventBus:::kernelSpace
     Postgres:::kernelSpace
     Executor:::kernelSpace
     Safety:::kernelSpace
     Scanner:::userSpace
     NewsAgent:::userSpace
     Portfolio:::userSpace
     InstAgents:::userSpace
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold
    classDef infraSpace fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold
    style Infrastructure_Layer fill:#FAFAFA,stroke:#F57C00,stroke-width:3px
    style Kernel_Layer fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style User_Layer fill:#FAFAFA,stroke:#3F51B5,stroke-width:3px
```

---

## 3. Topology B: The Sovereign Decision Stream (SDS)

**Primary Attribute:** Atomic Execution Velocity
**Ideal For:** Tactical Automation, Risk Stops, Reactive Decision-Making

> **A note on latency:** SDS minimizes decision latency *relative to multi-agent topologies* (EOAM), but it still involves LLM inference (typically 100ms-2s). It is not designed for microsecond-scale High-Frequency Trading (HFT), which requires deterministic code paths without probabilistic reasoning. SDS targets "fast-for-AI" decisions (sub-second to low-second), not "fast-for-hardware" decisions (sub-millisecond).

While the **Event-Oriented Agent Mesh (EOAM)** excels at multi-perspective coordination and organizational "Digital Twins," it introduces significant latency and computational overhead due to its reliance on parallel orchestration and arbitration.

The **Sovereign Decision Stream (SDS)** is an alternative architectural pattern designed for low-latency, cost-efficient, and structurally safe decision-making. SDS treats the decision process as a "straight-line" function rather than a choreographic dialogue. It achieves structural safety not through post-generation validation (the "Audit" model), but through **Constrained Decoding**-embedding the deterministic rules of the **Decision Intelligence Runtime (DIR)** directly into the probabilistic sampling of the Large Language Model.

### 3.1 The SDS Philosophy: "Syntactically Bound by Design"

> **Mandatory Disclaimer:** Constrained Decoding (Grammar-based sampling) ensures structural integrity and boundary adherence but **DOES NOT** guarantee semantic alignment with the ROA Mission. Final semantic and safety validation remains the exclusive responsibility of the DIR Decision Integrity Module (DIM).

In the SDS topology, the separation between User Space (Reasoning) and Kernel Space (Validation) remains architecturally absolute, but becomes executionally transparent. SDS replaces the "Thundering Herd" of parallel agents with a single, high-context **Decision Atom**.

#### 3.1.1 Constrained Decoding (The Safety Straightjacket)

The cornerstone of SDS is the use of grammars (e.g., via libraries like *Outlines* or *Guidance*) to enforce the **Responsibility Contract** during inference.

*   **Deterministic Sampling:** The LLM is physically unable to generate a token that violates the JSON schema or numerical bounds defined by the DIR.
*   **Elimination of Syntax Errors:** Because the output is constrained by a state machine, the resulting **PolicyProposal** is guaranteed to be syntactically valid and semantically bounded before it even reaches the Runtime.

#### 3.1.2 The "Atomic Context": Input to Inference

In SDS, there is no emergent context or asynchronous message passing. The **Context Compiler** assembles an **Atomic Context**-a pre-validated package containing:

1.  **The Mission** (from ROA).
2.  **The Constraints** (from DIR Hard Gates).
3.  **The Snapshot** (from the Context Store).

**Critical Binding:** The Agent's output (The Intent) **MUST** include the `ContextSnapshotID` hash-binding from the input. The DIR verifies this JIT to prevent execution against a drift-unverified state. The combination of the **Atomic Context**, the **Intent**, and the **Signature** forms the final **Decision Atom**.

### 3.2 The SDS Decision Lifecycle

The SDS lifecycle collapses the multi-agent choreography of EOAM into a streamlined, four-stage pipeline.

1.  **Ingest & Compile:** A trigger event initializes a **DecisionFlow (DFID)**. The Runtime compiles the "Decision Atom," injecting authority limits directly into the prompt metadata.
2.  **Constrained Reasoning (SDS Loop):** The agent performs its **Explain** phase. When transitioning to the **Policy** phase, the inference engine switches to a constrained mode, utilizing the DIR-provided grammar to ensure the proposal is "**Syntactically Bound by Design**".
3.  **JIT Fast-Pass Validation:** Because the proposal was generated under constraint, the **Decision Integrity Module (DIM)** performs only a lightweight **Just-In-Time (JIT) State Verification** to check for environment drift since the snapshot.
4.  **Execution:** The **PolicyProposal** is immediately transformed into an **Execution Intent**.

```mermaid
---
title: "Topology B: SDS Decision Lifecycle"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart LR
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;
    classDef infraSpace fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold;

    Trigger((Signal)) --> Atom
    
    subgraph Compile ["`**1. INGEST & COMPILE**`"]
        Atom["`**Decision Atom**<br/>Snapshot + Limits`"]:::kernelSpace
    end

    subgraph Constrained_Loop ["`**2. CONSTRAINED REASONING**`"]
        Grammar["`**Grammar**<br/>(Straightjacket)`"]:::kernelSpace
        Inference(["`**LLM Inference**<br/>Syntactically Bound`"]):::userSpace
        
        Grammar -.-> Inference
        Atom --> Inference
    end

    subgraph Fast_Pass ["`**3. JIT FAST-PASS**`"]
        JIT{"`**Lightweight JIT**<br/>Drift Check`"}:::kernelSpace
    end
    
    subgraph Exec_Layer ["`**4. EXECUTION**`"]
        Intent["`**Execution Intent**<br/>Atomic Action`"]:::infraSpace
    end

    Inference -->|Valid Proposal| JIT
    JIT -->|Pass| Intent

    style Compile fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style Constrained_Loop fill:#FAFAFA,stroke:#3F51B5,stroke-width:3px
    style Fast_Pass fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style Exec_Layer fill:#FAFAFA,stroke:#F57C00,stroke-width:3px
```

### 3.3 Holistic SDS Architecture (High-Performance Implementation)

The following diagram illustrates a complete **Sovereign Decision Stream (SDS)** architecture, designed for maximum throughput and minimal latency. It highlights the direct path from observation to execution, bypassing the complex event bus choreography of EOAM while maintaining strict safety via the "Straightjacket" grammar.

```mermaid
---
config:
  layout: dagre
  theme: neutral
  look: classic
title: Holistic SDS Architecture (Tactical Automation)
---
flowchart LR
 subgraph Data_Sources["**Data Sources**"]
    direction TB
        L1_Feed["L1/L2 Market Data"]
        Tick_Stream["Tick Stream"]
  end
 subgraph Infrastructure_Layer["**INFRASTRUCTURE SPACE**<br>Low-Latency I/O"]
    direction LR
        Data_Sources
        Direct_DMA["DMA Gateway"]
        Dashboard["Risk Console"]
  end
 subgraph Kernel_Layer["**KERNEL SPACE (DIR)**<br>Validation &amp; Compilation"]
    direction TB
        Context_Compiler["Context Compiler"]
        Grammar_Factory["Grammar Factory"]
        JIT_Validator["JIT Validator"]
        Executor["Atomic Executor"]
        Risk_Governor["Risk Governor"]
        Registry[("Agent Registry")]
  end
 subgraph User_Layer["**USER SPACE (SDS)**<br>Constrained Reasoning"]
    direction LR
        HFT_Agent(["Tactical Agent"])
        Inference_Engine[["LLM Inference Engine"]]
  end
    L1_Feed & Tick_Stream ==> Context_Compiler
    Registry -.-> Grammar_Factory
    Context_Compiler -- Atomic Context --> HFT_Agent
    Grammar_Factory -- JSON Grammar --> Inference_Engine
    HFT_Agent -- "Prompt + Context" --> Inference_Engine
    Inference_Engine -- "Syntactic Policy" --> HFT_Agent
    HFT_Agent -- "Decision Atom" --> JIT_Validator
    Registry -.-> Risk_Governor
    Risk_Governor -.-> JIT_Validator
    JIT_Validator -- "Verified Intent" --> Executor
    Executor ==> Direct_DMA
    Direct_DMA -.-> Dashboard
    Context_Compiler -.-> JIT_Validator

     L1_Feed:::infraSpace
     Tick_Stream:::infraSpace
     Direct_DMA:::infraSpace
     Dashboard:::infraSpace
     Context_Compiler:::kernelSpace
     Grammar_Factory:::kernelSpace
     JIT_Validator:::kernelSpace
     Executor:::kernelSpace
     Risk_Governor:::kernelSpace
     Registry:::kernelSpace
     HFT_Agent:::userSpace
     Inference_Engine:::userSpace
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold
    classDef infraSpace fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold
    style Infrastructure_Layer fill:#FAFAFA,stroke:#F57C00,stroke-width:3px
    style Kernel_Layer fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style User_Layer fill:#FAFAFA,stroke:#3F51B5,stroke-width:3px
```

### 3.4 Design Intent: The "Fly-by-Wire" Paradigm

To visualize **Topology B**, consider the control system of a modern **Fighter Jet** (Fly-by-Wire).

In older aircraft (like standard scripts), the pilot's stick was mechanically connected to the wings. If the pilot pulled too hard, the wings could snap off. In a Fly-by-Wire system, there is no mechanical link.

*   **The Pilot (The Agent)** inputs an intent ("Pull up").
*   **The Flight Computer (The Grammar)** intercepts the signal. It knows the airframe's structural limit is 9G. Any stick input that would exceed that envelope is **rejected at the input layer** — the control surfaces physically will not respond to it. The pilot must issue a command *within* the safe envelope for the system to act.
*   **The Result:** The pilot retains full authority within the safe flight envelope, but the physics of the system make it impossible to exceed structural limits, regardless of intent.

**Topology B** applies this to decision-making. The Agent has "Sovereign" speed and authority, but it operates through a **Grammar**. It does not matter if the LLM's probability distribution favors trading 1,000,000 lots; the Grammar **masks that token at the sampling layer**, making it impossible to generate. The LLM must select from the remaining valid tokens. This allows the system to operate at high speeds (skipping the slow "Manager Review") because the "Physics of the System" (Syntax/Grammar) guarantees structural integrity.

---

## 4. Topology C: The Decision Ledger (DL+PCI)

**Primary Attribute:** Formal Verification & Absolute Audit
**Ideal For:** Compliance-Heavy Operations, Inter-Organizational Settlements, High-Value Transfers

**Topology C** represents the ultimate stage of formal verification within the Decision Intelligence Runtime framework. It shifts the focus from "trusting the agent" (EOAM) or "constraining the agent" (SDS) to **"verifying the artifact."**

### 4.1 The Philosophy: Proof-Carrying Intents (PCI)

In this model, the system operates on a "Zero-Trust" basis regarding the agent's reasoning process. The **Decision Ledger** does not execute an intent because an agent "said so"; it executes it only if the intent carries an immutable proof of compliance.

This transitions the architecture from **Active Agents** to **Proof-Carrying Intents (PCI)**. The safety is a property of the data structure itself, not the process that generated it.

### 4.2 The Decision Ledger

The **Decision Ledger** is an append-only, immutable record that serves as the "Immutable Source of Truth" for the system.

*   **Append-Only:** History cannot be rewritten. Every decision, whether successful or rejected, is permanently recorded.
*   **Idempotency:** The Ledger ensures that replaying the same intent results in the same outcome (or a deterministic rejection if state has changed).
*   **Zero-Trust Auditability:** Auditors do not need to inspect the LLM's "thoughts"; they only need to verify the cryptographic proofs stored in the Ledger.

> The cryptographic protocol for generating and verifying Evidence Hashes and PCIs is formally specified in the **Technical Annex** at the end of this document.

### 4.3 The Proof Checker

In Topology C, the **Decision Integrity Module (DIM)** acts as a minimalist **Proof Checker**. It does not "think" or "reason." It simply validates the proofs attached to the intent.

*   **Cryptographic Verification:** Verifies the signature of the intent (binding it to an ROA identity).
*   **Logical Verification:** Checks that the intent includes valid evidence for all required rules (e.g., "RBAC Check Passed," "Limit Check Passed," "State Freshness Verified").
*   **Temporal Validity (Drift Check):** Explicitly verifies that the `ContextSnapshotID` referenced in the PCI is not "stale" (expired timestamp) and that the live system state has not drifted beyond the allowable envelope since the proof was generated.

### 4.4 Concept Refinement: PCI vs. Decision Atom

**Proof-Carrying Intent (PCI)** is an evolution of the "Decision Atom" from SDS.

*   **Decision Atom:** Contains **What** (Action) and **Context** (Snapshot). Guaranteed to be *syntactically* valid by SDS.
*   **Proof-Carrying Intent:** Contains **What**, **Why** (Semantic Rationale), and **Proof** (Deterministic evidence). Guaranteed to be *formally* compliant against the Ledger's history.

While SDS ensures the agent stays within *syntactic* bounds (e.g., "produce valid JSON"), DL+PCI ensures **formal compliance** (e.g., "this transfer is valid because the balance was X at block Y, and policy Z allows transfers under limit L").

```mermaid
---
title: "Topology C: Component Architecture & Proof Flow"
config:
  layout: elk
  theme: neutral
  look: classic
---
flowchart TB
    classDef userSpace fill:#E8EAF6,stroke:#3F51B5,stroke-width:2px,color:#1A237E,font-weight:bold;
    classDef kernelSpace fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20,font-weight:bold;
    classDef infraSpace fill:#FFF3E0,stroke:#F57C00,stroke-width:2px,color:#E65100,font-weight:bold;

    subgraph User_Space ["`**USER SPACE**`"]
        Prover(["`**Prover Agent**<br/>(Signer)`"]):::userSpace
    end

    subgraph Kernel_Space ["`**KERNEL SPACE (DIR)**`"]
        direction TB
        
        subgraph Authorities ["`**Reference Authorities**`"]
            Registry[("`**Agent Registry**<br/>Contract Hash ($H_c$)`")]:::kernelSpace
            Context[("`**Context Store**<br/>State Hash ($H_s$)`")]:::kernelSpace
        end

        subgraph Validation_Gate ["`**Verification**`"]
            DIM{"`**DIM / Proof Checker**<br/>Verify Evidence Hash`"}:::kernelSpace
        end

        Ledger[("`**Decision Ledger**<br/>Immutable Log`")]:::kernelSpace
    end

    subgraph Infra_Space ["`**INFRASTRUCTURE**`"]
        Executor["`**Execution Engine**<br/>Deterministic Side-Effect`"]:::infraSpace
    end

    %% Data Flow
    Prover -->|"`**Submit PCI**<br/>(Intent + Proof + Sig)`"| DIM
    
    Registry -.->|"$H_c$"| DIM
    Context -.->|"$H_s$"| DIM
    
    DIM -->|"`**Valid**`"| Ledger
    DIM -.->|"`**Invalid**`"| Reject((Reject)):::kernelSpace
    
    Ledger ==>|"`**Commit Event**`"| Executor

    style User_Space fill:#FAFAFA,stroke:#3F51B5,stroke-width:3px
    style Kernel_Space fill:#FAFAFA,stroke:#388E3C,stroke-width:3px
    style Infra_Space fill:#FAFAFA,stroke:#F57C00,stroke-width:3px
    style Authorities fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,stroke-dasharray: 5 5
    style Validation_Gate fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,stroke-dasharray: 5 5
```

### 4.5 Addressing the Obvious Question: "Is Topology C Just Topology B With Extra Steps?"

A natural objection arises: if a Proof-Carrying Intent builds on top of SDS's Decision Atom, isn't Topology C merely Topology B with an additional audit layer? The answer is no-and the distinction is architectural, not incremental.

The three topologies differ not only in **Signal Flow** (how messages move) but in **Trust Locus** (where safety is guaranteed):

| Property | Topology A (EOAM) | Topology B (SDS) | Topology C (DL+PCI) |
| :--- | :--- | :--- | :--- |
| **Trust Locus** | **Process** — DIM validates *after* agents reason | **Generation** — Grammar constrains *during* inference | **Artifact** — PCI carries proof *within itself* |
| **Offline Verifiability** | No — requires live DIM and Runtime | No — requires live JIT and Runtime | **Yes** — PCI is self-contained and cryptographically verifiable |
| **Recovery Model** | Re-arbitrate (select new winner from proposals) | Re-reason (trigger new LLM inference) | **Deterministic Replay** from immutable Ledger |
| **Inter-Organizational Use** | No — confined to a single trust domain | No — Grammar and JIT are internal | **Yes** — PCI can be verified by an external auditor or counterparty |

#### Why This Matters: The Regulatory Audit Scenario

Consider a concrete scenario that exposes the architectural difference:

> **Six months after execution, a regulator asks: "Why did the system sell 500 shares of XYZ on March 15th at 14:32?"**
>
> *   **Topology B (SDS):** The Runtime has logs. The DFID links the trigger to the action. But the JIT check was performed by a Runtime that has since undergone three software updates. The auditor must *trust* that the logs were not altered and that the validation logic at the time of execution matched the current version. The proof is *reconstructed* from system state-it was never an independent object.
> *   **Topology C (DL+PCI):** The auditor retrieves the PCI from the immutable Decision Ledger. They re-calculate the `evidence_hash` using the archived $H_s$, $H_c$, and $H_r$. They verify the `roa_signature` against the registered public key. **No access to the live Runtime is required.** The proof is a *property of the artifact*, not a property of the system that produced it.

This is not "B plus logging." It is a fundamentally different trust architecture:

*   **SDS guarantees:** "This intent was structurally valid *at the moment of generation*."
*   **DL+PCI guarantees:** "This intent was formally compliant, and *anyone can verify this at any time*, without trusting the system that produced it."

The distinction mirrors the difference between **runtime type-checking** (safe while the program runs) and **proof-carrying code** (safe regardless of the execution environment). Both are valid; they serve different classes of problems. Topology C exists for scenarios where the proof must *outlive* the system that generated it.

### 4.6 Design Intent: The "Notarized Execution" Paradigm

To better understand Topology C, consider the banking concept of a **Letter of Credit (L/C)** (PL: *Akredytywa*).

In a standard transaction, a buyer might promise to pay. In an L/C, a **Bank** (The Runtime) guarantees payment to a **Beneficiary** (Execution) on behalf of a **Buyer** (The Agent), *provided that* specific documents (Proofs) are presented.

*   **The Agent (Buyer)** does not touch the money directly. It instructs the bank.
*   **The Runtime (Bank)** does not judge the quality of the goods. It strictly verifies that the *documents* (Bill of Lading, Invoice) match the conditions of the Credit exactly.
*   **The Execution (Beneficiary)** gets paid (action executes) *if and only if* the documents are perfect.

In **Topology C**, the **Proof-Carrying Intent (PCI)** is that "stack of documents." The Agent (Buyer) constructs a complex transaction, but the Runtime (Bank) will only "release funds" (execute side effects) if the cryptographic proofs (documents) perfectly match the **Decision Ledger's** requirements. If a single signature is missing or a timestamp is stale, the transaction is dishonored-regardless of how "smart" the Agent's reasoning was.

This transforms the system from **"Trust but Verify"** (classic agent monitoring) to **"Verify then Trust"** (cryptographic enforcement).

---

## 5. Comparative Analysis: The Decision Matrix

The choice between EOAM, SDS, and DL+PCI is a strategic decision based on the trade-off between **Coordination**, **Velocity**, and **Integrity**. These three dimensions form a "pick-two" triangle analogous to the **CAP Theorem** in distributed systems: optimizing for one axis necessarily constrains the others.

```mermaid
---
title: "The Decision Triangle: Coordination × Velocity × Integrity"
config:
  theme: neutral
  look: classic
---
flowchart LR
    classDef coordStyle fill:#E8EAF6,stroke:#3F51B5,stroke-width:3px,color:#1A237E,font-weight:bold;
    classDef velocStyle fill:#FFF3E0,stroke:#F57C00,stroke-width:3px,color:#E65100,font-weight:bold;
    classDef integStyle fill:#E8F5E9,stroke:#388E3C,stroke-width:3px,color:#1B5E20,font-weight:bold;
    classDef edgeLabel fill:none,stroke:none,color:#616161,font-style:italic;

    EOAM(["`**Topology A: EOAM**
    COORDINATION
    *(breadth & strategy)*`"]):::coordStyle

    SDS(["`**Topology B: SDS**
    VELOCITY
    *(speed & tactics)*`"]):::velocStyle

    DL(["`**Topology C: DL+PCI**
    INTEGRITY
    *(trust & audit)*`"]):::integStyle

    EOAM ---|"Trade-off: Speed vs Breadth"| SDS
    SDS ---|"Trade-off: Rigor vs Speed"| DL
    DL ---|"Trade-off: Breadth vs Rigor"| EOAM
```

| Feature | Event-Oriented Agent Mesh (EOAM) | Sovereign Decision Stream (SDS) | Decision Ledger (DL+PCI) |
| :--- | :--- | :--- | :--- |
| **Primary Goal** | **Coordinated Strategic Reasoning** | Atomic execution velocity | **Formal Verification / Absolute Integrity** |
| **Topology Type** | Decentralized Choreography (Many-to-Many) | Linear Pipeline (One-to-One) | Append-Only Log (State-to-State) |
| **Trust Locus** | **Process** — Runtime validates after generation | **Generation** — Grammar constrains during inference | **Artifact** — PCI carries self-contained proof |
| **Offline Verifiability** | No (requires live DIM) | No (requires live JIT) | **Yes** (self-contained cryptographic proof) |
| **Concurrency** | High (Parallel Reasoning) | Low (Linear Atomic Decision) | Serialized (Ledger Ordering) |
| **Latency** | Significant (Priority-Based Preemption) | **Minimal** (Single Inference Pass) | Medium (Log persistence & proof verification) |
| **Cost** | High (Multi-agent activation) | **Low** (Token-optimized single call) | Medium (Proof generation overhead) |
| **Recovery Model** | Re-arbitrate (select new proposal winner) | Re-reason (new LLM inference) | **Deterministic Replay** (from immutable Ledger) |
| **Inter-Org Use** | No (single trust domain) | No (internal Grammar & JIT) | **Yes** (PCI verifiable by external party) |
| **Ideal Case** | Strategic Portfolio Rebalancing | Tactical Automation / Risk Stops | **Compliance-heavy ops, Settlements** |

---

## 6. Implementation Blueprints

A robust **Decision Intelligence** system can support all topologies simultaneously within the same **Agent Registry**.

### 6.1 Topology A: Mesh Handler (EOAM)

```python
# agents/trader_mesh_agent.py
class TacticalTrader(ResponsibleAgent):
    def register(self):
        # Register for semantic routing
        self.registry.handshake(self.agent_id, contract, topology="EOAM")

    def on_observation(self, event: ObservationEvent):
        # 1. Mesh Logic: Reactive, Parallel
        context = ContextCompiler.assemble(event.snapshot_id)
        explanation = self.llm.explain(context, self.mission)
        policy_intent = self.llm.generate_policy(context, explanation)
        
        # 2. Emit Proposal to Bus for Preemption/Selection
        proposal = PolicyProposal(
            dfid=event.dfid,
            params=policy_intent,
            constraints={"drift_envelope_bps": 50}, # JIT Drift Parameter
            context_ref=event.snapshot_id
        )
        EventBus.publish(proposal) 
```

### 6.2 Topology B: Stream Handler (SDS)

```python
# sds/core_handler.py
from outlines import models, generate
from pydantic import BaseModel, Field

class SDSExecutionConstraints(BaseModel):
    # The DIR-enforced 'Straightjacket'
    max_trade_size: float = Field(le=1000.0) # Absolute DIR Hard Gate
    authorized_instruments: list[str] = ["BTC-USD", "ETH-USD"]

class SDSPolicy(BaseModel):
    action: str # Must match Literal ["BUY", "SELL", "HOLD"]
    amount: float
    rationale: str # The 'Explain' component

def execute_sovereign_stream(dfid: str, context_snapshot: dict):
    # 1. Fetch Mission and Constraints from Registry & DIR
    contract = AgentRegistry.get_contract(context_snapshot.agent_id)
    
    # 2. Build the 'Decision Atom' Grammar
    # This prevents the LLM from ever suggesting > 1000.0 or unauthorized assets
    grammar = build_pydantic_grammar(SDSPolicy, constraints=contract.limits)
    
    # 3. Constrained Inference (The SDS Secret Sauce)
    # The model samplers are gated by the DIR-defined grammar
    policy_proposal = generate.json(model, grammar)(
        prompt=f"Mission: {contract.mission}\nContext: {context_snapshot.data}"
    )
    
    # 4. JIT Verification & Execution (Minimal Latency)
    # Requires hash-binding check against context_snapshot
    return DIR.jit_execute(dfid, policy_proposal, context_snapshot.hash)
```

### 6.3 Topology C: Ledger Handler (DL+PCI)

```python
# sds/ledger_intent_compiler.py
class ProofCarryingIntent(BaseModel):
    dfid: str
    intent: SDSPolicy # Syntactically bound
    proof: dict = {
        "rule_checks": ["RBAC", "LIMITS", "FRESHNESS"],
        "evidence_hash": "sha256_of_state_and_contract"
    }
    signature: str # Cryptographic bond to ROA identity

class ProofChecker:
    def verify(self, pci: ProofCarryingIntent, ledger: DecisionLedger):
        # 1. Cryptographic Verification
        if not self.verify_signature(pci.signature, pci.dfid):
            raise InvalidSignatureError()

        # 2. Logical Verification
        # Does the evidence hash match the current ledger state?
        current_state_hash = ledger.get_state_hash()
        if pci.proof["evidence_hash"] != current_state_hash:
             raise StateDriftError("Proof invalid for current state")
             
        # 3. Commit
        ledger.append(pci)
        return True
```

### 6.4 Kernel-User Space Integrity Constraints (All Topologies)

The following constraints apply **regardless of topology**. They are properties of the DIR Kernel, not of any specific signal flow pattern. They are included here because they govern the boundary between all Implementation Blueprints above and the Execution Engine.

*   **Deterministic Compensation Menu:** In multi-step decisions, agents MUST NOT generate "reasoning-based compensation" logic. Instead, they must select from a pre-defined, DIR-validated set of actions (e.g., `REVERT`, `CLOSE_ALL`, `ALERT_HUMAN`). This prevents the same reasoning capability that caused the failure from exacerbating it.
*   **Lock Normalization:** Agents are NOT responsible for sorting Resource IDs to prevent deadlocks. **Alphabetical lock normalization is a Kernel (Runtime) responsibility**, ensuring that the Reasoning layer remains infrastructure-agnostic.

---

## 7. Conclusion

The development of **Decision Intelligence Topologies** marks the maturation of agentic engineering. We are moving beyond the era of treating Large Language Models as meaningful entities in themselves, and towards an era where they are components within rigorous system architectures.

The inclusion of **Topology C (DL+PCI)** completes the triad-not as an incremental extension of earlier patterns, but as a fundamentally different **Trust Locus**:
*   **EOAM** for breadth and strategy — safety lives in the **process**.
*   **SDS** for speed and tactics — safety lives in the **generation**.
*   **DL+PCI** for truth and audit — safety lives in the **artifact**.

Sophisticated organizations will employ all three topologies in concert. The Mesh (EOAM) thinks deeply about strategy and risk; the Stream (SDS) executes those strategies with precision; and the Ledger (DL) records the irrevocable truth of every action-a truth that can be verified by any party, at any time, without access to the system that produced it. In all cases, the future belongs to architectures that prioritize **auditability over creativity** and **constraints over capabilities**.

---

## 8. Glossary

*   **Priority-Based Preemption (EOAM):** A mechanism where the Runtime selects the "winning" proposal based on the **Agent Registry Priority Matrix** (e.g., Risk > Strategy) rather than just a time window.
*   **Constrained Decoding (SDS):** Using grammar-based sampling to physically prevent an LLM from generating non-compliant tokens.
*   **Drift Envelope:** A contract-level parameter specifying the maximum allowable deviation (e.g., price slippage, latency) for JIT Verification before a PolicyProposal is rejected.
*   **DecisionFlow ID (DFID):** The immutable trace ID linking observation, reasoning, and execution.
*   **Decision Intelligence Runtime (DIR):** The deterministic kernel validating all agent actions.
*   **Decision Atom (SDS):** A single, context-complete package for atomic execution, hash-bound to a specific snapshot.
*   **Event-Oriented Agent Mesh (EOAM):** A decentralized topology for parallel, multi-agent coordination.
*   **Responsibility-Oriented Agent (ROA):** The identity layer defining "Who" is reasoning.
*   **Sovereign Decision Stream (SDS):** A linear topology for high-velocity, atomic decisions.
*   **Wake-up Predicate:** cheap heuristic logic used to suppress signals before invoking expensive agents.
*   **Decision Ledger:** An append-only, immutable record serving as the source of truth for all decisions.
*   **Proof-Carrying Intent (PCI):** An intent artifact containing action, rationale, and deterministic proof of rule compliance.
*   **Proof Checker:** A minimalist verification module that validates PCI proofs without reasoning.
*   **Immutable Narrative:** The unchangeable history of decisions and states stored in the Decision Ledger.
*   **Trust Locus:** The architectural location where safety is guaranteed within a given topology: the **Process** (EOAM — runtime validates after generation), the **Generation** (SDS — grammar constrains during inference), or the **Artifact** (DL+PCI — the PCI carries self-contained, cryptographically verifiable proof).

---

# Technical Annex: Cryptographic Integrity for Topology C (DL+PCI)

## 1. Abstract

This technical annex defines the protocol for generating and verifying the **Evidence Hash** and **Proof-Carrying Intents (PCI)** within the **Decision Ledger** topology. As established in the **Decision Intelligence Topologies** whitepaper, Topology C moves the system from "Active Reasoning" to "Formal Verification," where safety is a structural property of the intent artifact itself.

The primary objective is to ensure that every entry in the **Decision Ledger** is cryptographically bound to a specific version of reality (**Context Snapshot**), a specific authority (**Responsibility Contract**), and a deterministic result from the **Proof Checker**.

---

## 2. The Proof-Carrying Intent (PCI) Structure

A **Proof-Carrying Intent** is the definitive communication primitive for Topology C. It encapsulates the probabilistic reasoning of the agent within a deterministic, verifiable envelope.

| Field | Type | Description |
| --- | --- | --- |
| `dfid` | UUID | The immutable **DecisionFlow ID** linking the intent to its causal trigger. |
| `intent_payload` | JSON | The **Syntactically Bound** policy generated via SDS Constrained Decoding. |
| `context_ref` | Hash | The **ContextSnapshotID** representing the "frozen reality" used during reasoning. |
| `evidence_hash` | Hash | The composite hash proving alignment between state, contract, and rules. |
| `roa_signature` | Signature | The cryptographic signature of the agent, verifying identity and authority. |

---

## 3. Evidence Hash Generation Protocol

The **Evidence Hash** is not a simple checksum; it is a **Merkle-root-style** derivation that ensures any drift in context or unauthorized changes to the mission results in an immediate verification failure.

### 3.1 Components of the Hash

The hash is derived from three immutable inputs provided by the **Decision Intelligence Runtime (DIR)**:

1. **State Snapshot Hash ($H_s$):** The SHA-256 hash of the `ContextSnapshotID`.
2. **Contract Hash ($H_c$):** The SHA-256 hash of the **Responsibility Contract** active in the **Agent Registry** at $T_{start}$.
3. **Rule-Set Hash ($H_r$):** The hash of the deterministic validation rules (Hard Gates) applied by the DIM.

### 3.2 Derivation Formula

The `evidence_hash` ($H_{evidence}$) is calculated as follows:

$$ H_{evidence} = \text{SHA256}( \text{DFID} \parallel H_s \parallel H_c \parallel H_r ) $$

This ensures that the proof is unique to the specific **DecisionFlow** and cannot be replayed in a different context or by an agent with a different contract.

---

## 4. The Proof Checker Workflow

In Topology C, the **Decision Integrity Module (DIM)** functions as a minimalist **Proof Checker**. It executes the following deterministic steps before committing the intent to the **Decision Ledger**:

1. **Identity Attestation:** Verifies that the `roa_signature` matches the public key registered in the **Agent Registry**.
2. **Context Binding:** Retrieves the current system state and verifies that the `context_ref` in the PCI matches the `ContextSnapshotID` generated at the start of the flow.
3. **JIT Drift Verification:** Performs a final check to ensure the live environment state is within the **Drift Envelope** defined in the contract.
4. **Hash Validation:** Re-calculates the `evidence_hash` using the Registry's authoritative data and compares it against the hash provided in the PCI.
5. **Commitment:** If all checks pass, the PCI is appended to the **Decision Ledger**, and the **Execution Engine** is triggered.

```mermaid
---
title: "Topology C: Proof Verification Sequence"
config:
  theme: neutral
  look: classic
---
sequenceDiagram
    participant A as Prover Agent (SDS)
    participant K as Proof Checker (Kernel)
    participant L as Decision Ledger (Immutable)
    participant E as Execution Engine

    Note over A: Generates Syntactic Intent<br/>+ Evidence Hash
    A->>K: Submit PCI (Intent + Proof)
    
    activate K
    K->>K: Verify Signature
    K->>K: Validate Evidence Hash<br/>(State + Contract + Rules)
    K->>K: JIT Drift Check<br/>(within Envelope?)
    
    alt Verification Passed
        K->>L: Append PCI to Ledger
        K->>E: Trigger Deterministic Action
        E-->>K: Success (ResultID)
        K-->>A: Closed (Status: Success)
    else Verification Failed
        K-->>A: Aborted (Status: REJECT_DRIFT / REJECT_AUTH)
    end
    deactivate K

```

---

## 5. Resilience: Handling State Disruption

Topology C utilizes the **Decision Ledger** to manage failures without relying on probabilistic agent reasoning.

* **Audit Trait:** Because every intent is a PCI, the Ledger provides a "Zero-Trust" audit trail. If a system failure occurs, the Ledger allows for a **Deterministic Replay** to identify exactly which proof failed.
* **Immutable Compensation:** If an execution fails after the Ledger commitment (e.g., Infrastructure error), the system triggers a **Deterministic Compensation Action** from a pre-defined menu (e.g., `REVERT_STATE`), rather than asking the agent to re-reason about the failure.
* **Registry Outage:** During a Registry outage, the Proof Checker relies on **Local Manifest Caching**. However, new PCIs requiring authority updates are rejected to prevent **Stale Authority Exploitation**.

---

## 6. Conclusion

The **Evidence Hash** and **Proof-Carrying Intent** represent the most rigorous layer of the **Decision Intelligence Runtime**. By treating safety as a cryptographic requirement of the artifact, Topology C ensures that even the most advanced Large Language Models remain "Provers" of intent rather than "Owners" of execution. This annex provides the technical substrate for a system where truth is found in the **Ledger**, and agents are held to an immutable standard of formal compliance.
