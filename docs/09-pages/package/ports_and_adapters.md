---
title: Ports and Adapters
nav_order: 4
---

# Ports and Adapters

The `dir-core` package embraces **Hexagonal Architecture**. It defines the rules and protocols (Ports) but delegates technical responsibilities to external implementations (Adapters). 

This section explains how to inject custom implementations for Storage, Contracts, LLMs, and Event Buses into `dir-core`.

## 1. Storage and Context (`dir_core.storage.base`)

The Kernel Space relies on external storage to persist the Agent Registry and Context state. `dir-core` provides the following Protocols:

- `AgentRegistryStorage`: Responsible for persisting `ResponsibilityContracts` and tracking agent statuses (e.g., `ACTIVE`, `SUSPENDED`).
- `ContextStorage`: Responsible for storing `ContextSnapshots` bound to specific DFIDs.

### Injecting Storage Adapters

To use a custom database (like PostgreSQL or MongoDB), implement these protocols and bundle them via the `StorageBundle`:

```python
from dir_core.storage.base import AgentRegistryStorage, ContextStorage, StorageBundle

class PostgresRegistry(AgentRegistryStorage):
    def get_agent_contract(self, agent_id: str) -> dict:
        # SQL logic here
        pass
    # ... implement other methods

class PostgresContext(ContextStorage):
    def save_snapshot(self, dfid: str, data: dict) -> str:
        # SQL logic here
        pass
    # ... implement other methods

# Bundling for the core
custom_storage = StorageBundle(
    agent_registry=PostgresRegistry(conn),
    context=PostgresContext(conn)
)

# Injecting into dir-core components
registry = AgentRegistry(storage=custom_storage.agent_registry)
store = ContextStore(storage=custom_storage.context)
```

For a concrete reference implementation of a **PostgreSQL** storage adapter, see the sample in [samples/08_custom_repo_psql/](../../../samples/08_custom_repo_psql/README.md).

*(Note: `dir-core` provides `sqlite_storage` and `memory_storage` as lightweight defaults).*

## 2. Responsibility Contracts

A `ResponsibilityContract` dictates an agent's boundaries. Rather than hardcoding how these contracts are loaded, applications should implement a `ContractProvider`.

### Injecting a Contract Provider

A `ContractProvider` fetches the Pydantic model representation of a contract from an external source:

```python
from abc import ABC, abstractmethod
from dir_core.models import ResponsibilityContract

class ContractProvider(ABC):
    @abstractmethod
    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        pass

class OPAContractProvider(ContractProvider):
    def __init__(self, opa_url: str):
        self.opa_url = opa_url

    def get_contract(self, agent_id: str) -> ResponsibilityContract:
        # Fetch policy from Open Policy Agent (OPA) REST API
        # Map JSON response to ResponsibilityContract
        return ResponsibilityContract(
            agent_id=agent_id,
            mission=response["mission"],
            allowed_policy_types=response["allowed_actions"]
        )
```

## 3. Large Language Models (LLMs)

`dir-core` does **not** rely on `openai` or `langchain` packages. Instead, it defines a simple abstract base class for LLMs: `LLMClient(ABC)`.

### Injecting an LLM Client

Applications can wrap their preferred LLM SDK (OpenAI, Anthropic, Ollama, vLLM) in a thin adapter:

```python
from dir_core.utils.llm_client import LLMClient
from openai import OpenAI

class OpenAILlmClient(LLMClient):
    def __init__(self, api_key: str, model="gpt-4"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        
    def generate(self, prompt: str, system: str = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return response.choices[0].message.content
```

This ensures that upgrading LLM providers or switching to a `MockLLMClient` for unit testing requires **zero** changes to `dir-core` or the decision logic.

## 4. Event Bus (`dir_core.event_bus`)

For choreographing topologies like the **Event-Oriented Agent Mesh (EOAM)**, `dir-core` requires a pub/sub mechanism represented by the `EventBusProtocol`.

### Injecting an Event Bus

You can bridge standard enterprise message brokers (like Kafka, RabbitMQ, or AWS EventBridge) by creating an Adapter:

```python
from dir_core.event_bus import EventBusProtocol, SubscriptionHandler

class KafkaEventBus(EventBusProtocol):
    def __init__(self, bootstrap_servers: str):
        # Initialize Kafka Producer and Consumer
        pass
        
    def publish(self, topic: str, payload: dict) -> None:
        # Produce message to Kafka topic
        pass
        
    def subscribe(self, topic: str, handler: SubscriptionHandler) -> None:
        # Register a consumer group callback
        pass
```
