---
title: Overview
nav_order: 1
---

# `dir-core` - Decision Intelligence Runtime

**`dir-core`** is a technology-agnostic Python package providing the foundational Kernel Space for the Decision Intelligence Runtime (DIR). It acts as a deterministic Policy Enforcement Point (PEP) that governs the lifecycle, validation, and execution of decisions made by probabilistic AI agents.

## Philosophy: "The Wall"

At the heart of `dir-core` lies a strict architectural boundary known as **The Wall**, dividing systems into two distinct spaces:

1. **User Space (Probabilistic)**: The realm of Generative AI, Large Language Models, and business logic. Agents reason, analyze, and propose actions based on their assigned missions.
2. **Kernel Space (Deterministic)**: The realm of `dir-core`. A highly constrained, deterministic runtime that contains **no LLMs**. It validates proposals, enforces hard limits, and executes side effects.

`dir-core` operates exclusively in the Kernel Space. It does not dictate how your agents reason; it dictates **what they are allowed to do**.

## Hexagonal Architecture (Ports and Adapters)

`dir-core` is built using a strict **Hexagonal Architecture** (also known as Ports and Adapters). The core library is purely structural and logical. It defines the physics of the system through abstract interfaces (`Protocols` and `ABCs`), ensuring that the runtime is entirely decoupled from infrastructure concerns.

**Key benefits of this approach:**
- **Zero Lock-in**: You are not tied to a specific database (PostgreSQL vs. SQLite), an LLM provider (Ollama vs. OpenAI vs. Gemini), or a configuration format (YAML vs. JSON vs. REST API).
- **Testability**: Interfaces allow for seamless injection of in-memory mocks during unit testing or CI/CD pipelines.
- **Distributability**: The `dir-core` package is lean and lightweight, avoiding heavy infrastructure dependencies (like `psycopg2` or `SQLAlchemy`) unless explicitly chosen by the implementing application.

### The Core vs. The Adapters

| Domain | Port (Defined in `dir-core`) | Adapter (Injected from the outside) |
| :--- | :--- | :--- |
| **Storage** | `AgentRegistryStorage`, `ContextStorage` | `memory_storage`, `sqlite_storage`, Custom PostgreSQL |
| **LLM Inference** | `LLMClient(ABC)` | `OllamaClient`, `GeminiClient`, `MockLLMClient` |
| **Contracts** | `ResponsibilityContract` (Model) | `YamlContractProvider`, `DatabaseContractProvider` |
| **Event Bus** | `EventBusProtocol` | `InMemoryEventBus`, Custom Kafka / RabbitMQ |

## What `dir-core` IS

- A **Policy Enforcement Point (PEP)** that evaluates Agent proposals against formal `ResponsibilityContracts`.
- A **State Machine** for DecisionFlow lifecycles, ensuring full traceability via `DecisionFlow IDs (DFID)`.
- A **Protective Layer** applying constraints like JIT State Drift validation, Idempotency, and Rate Limiting (Intent Retry Governors).
- A set of **Pydantic Data Transfer Objects (DTOs)** defining the standard language for Agent-Kernel communication (`PolicyProposal`, `ExecutionIntent`).

## What `dir-core` IS NOT

- **It is not an LLM Orchestration Framework.** It does not compete with LangChain, CrewAI, or Autogen. Instead, it **wraps** them (via the Boxed Intelligence Pattern) to enforce safety limits.
- **It is not a Prompt Engineering Library.** It contains no prompts, no chains, and no system messages.
- **It is not an Infrastructure Provider.** It provides abstract Storage ports, but the responsibility of persisting data to distributed databases remains in the Application Space.

## Next Steps

- Proceed to [Architecture](architecture.md) to understand the deterministic lifecycle.
- Read [Ports & Adapters](ports-and-adapters.md) to see how to inject custom implementations.
- Explore [Core Components](core-components.md) for details on DIM, Registry, and Context.
