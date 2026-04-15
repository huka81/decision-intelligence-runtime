---
title: Core Components
nav_order: 5
---

# Core Components

The `dir-core` package provides a suite of deterministic tools that compose the **Kernel Space**. These components are orchestrated to enforce safety, track lifecycle states, and guarantee decision integrity.

## 1. Decision Integrity Module (DIM)

The **Decision Integrity Module (DIM)** is the heart of `dir-core`. It acts as a strict, rule-based gatekeeper evaluating agent output before any side effect occurs.

- **Input**: A `PolicyProposal` (a **Claim** of what the agent wants to do).
- **Processing**: The `validate_proposal` function checks the proposal against hardcoded rules.
- **Output**: Returns an `(ACCEPT, Reason)` or `(REJECT, Reason)` tuple.

### Validation Layers in DIM
1. **Schema Check**: Validates the payload against expected types (via Pydantic).
2. **Identity & Authority**: Verifies the `agent_id` against a list of `allowed_agents` or via the Agent Registry.
3. **Mission Dissonance**: Checks if the proposed action matches the agent's assigned Mission.
4. **Boundary Checks**: Ensures proposed values (e.g., `amount_usd`, `refund_percent`) do not breach limits defined in the `ResponsibilityContract`.
5. **State Drift Validation**: Ensures the world hasn't fundamentally changed between the moment the agent analyzed the state and the moment the proposal was submitted.

## 2. Agent Registry

The **Agent Registry** is the single source of truth for Agent identity, authority, and lifecycle state. Agents **cannot** self-register; they must be deployed into the Registry via an infrastructure pipeline (e.g., CI/CD).

### Key Functions:
- **Handshake**: Agents must perform a handshake at runtime to establish their presence. The Registry validates their `agent_version` and ensures their `ResponsibilityContract` is active.
- **Lifecycle Management**: Tracks whether an Agent is `ACTIVE`, `SUSPENDED`, or `RETIRED`. If an agent is suspended (e.g., due to a circuit-breaker tripping), the Registry will block any further actions.
- **Priority Resolution**: Assigns a `priority` level to agents, allowing the Event Bus to resolve conflicts when multiple agents attempt to act on the same event.

## 3. Context Store

The **Context Store** is a structured, deterministic repository that manages what an Agent "knows." In `dir-core`, Agents do not rely on conversational memory or unbounded context windows; they reason over certified snapshots.

### The Four Layers:
1. **Session Context**: Ephemeral state (e.g., the current API request payload or webhook event).
2. **State Context**: JIT-validated, high-fidelity facts (e.g., user account balance, active subscription status).
3. **Memory Context**: Long-term, immutable history of the Agent's past decisions and rationales.
4. **Artifacts Context**: Domain knowledge injected via RAG (e.g., policy PDFs, standard operating procedures).

When an Agent begins reasoning, the Context Compiler assembles these four layers into a **`ContextSnapshot`** which is securely hashed and bound to the DFID.

## 4. Event Bus

The **Event Bus** orchestrates asynchronous communications, specifically supporting **Topology A: Event-Oriented Agent Mesh (EOAM)**.

- **Topics & Subscriptions**: Agents subscribe to topics matching their Scope (e.g., `MARKET_DATA`, `USER_EVENTS`).
- **Wake-up Predicates**: To prevent expensive LLM calls on every event, the Event Bus evaluates lightweight deterministic rules (e.g., "Only wake the agent if price changes by >0.5%").
- **Arbitration**: If multiple agents emit a `PolicyProposal` for the same event, the Arbitrator queries the Agent Registry for priority matrices and selects the definitive winner.
