---
title: Installation
nav_order: 2
---

# Installation

`dir-core` is designed to be lightweight and strictly focused on deterministic runtime mechanics. It minimizes external dependencies, relying primarily on `pydantic` for strict data validation and `structlog` for structured logging.

## Prerequisites

- **Python 3.12+** is required.

## Installation

The `dir-core` package is available on PyPI:

```bash
pip install dir-core
```

### Installing from Source (Local Development)

For development or running the samples, you can install `dir-core` directly from the repository source in editable mode:

```bash
# Clone the repository
git clone https://github.com/huka81/decision-intelligence-runtime.git
cd decision-intelligence-runtime

# Install the core package in editable mode
pip install -e .
```

This installs `dir-core` globally within your active virtual environment, making it available as an importable module:

```python
from dir_core import PolicyProposal, ResponsibilityContract
from dir_core.dim import validate_proposal
```

## Dependencies

The `dir-core` package deliberately keeps its footprint small.

### Core Dependencies
Installed automatically when using `pip install .`:

- `pydantic >= 2.0`: Used extensively for enforcing data schemas, validating input/output, and defining models like `ResponsibilityContract` and `PolicyProposal`.
- `structlog`: Provides high-performance, structured JSON logging, enabling flawless DFID (DecisionFlow ID) correlation across distributed systems.

### Optional Dependencies (Adapters)

Because of its Hexagonal Architecture, `dir-core` does **not** install infrastructure libraries. If you choose to write adapters for external services, you must install the respective packages in your application environment.

**Examples of optional application-level dependencies:**
- For YAML configurations / contracts: `pip install pyyaml`
- For PostgreSQL storage: `pip install psycopg2-binary`
- For CrewAI Boxed Integration: `pip install crewai`
- For LangChain Boxed Integration: `pip install langchain langchain-ollama`
- For FastAPI HTTP APIs: `pip install fastapi uvicorn`

## Validating the Installation

You can verify the core is accessible by importing basic models and generating a new DecisionFlow ID (DFID):

```python
from dir_core import new_dfid
from dir_core.models import ResponsibilityContract

dfid = new_dfid()
contract = ResponsibilityContract(
    agent_id="test_agent",
    mission="Ensure system stability",
    allowed_policy_types=["MAINTENANCE"]
)

print(f"Generated DFID: {dfid}")
print(f"Contract Agent ID: {contract.agent_id}")
```

## Running Samples

The repository includes a comprehensive suite of samples demonstrating the runtime in action. To run them, make sure you have cloned the repository and installed the dependencies from the repository root:

```bash
pip install -e .
pip install -r requirements.txt
```

Then, you can execute any sample from the **repository root**:

```bash
python samples/00_quick_start/run.py   # Quick Start (recommended)
# or
python samples/01_roa_agent/run.py
# or
python samples/31_finance_trading/run.py
```

For the complete list of available samples and detailed explanations of their specific use cases, refer to the [Samples overview](../samples/index.md).
