# Contributing to Decision Intelligence Runtime (DIR)

First off, thank you for considering contributing to the Decision Intelligence Runtime (DIR) and the Responsibility-Oriented Agency (ROA) ecosystem. It's people like you that make open source such a great community.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue on GitHub. Please include:
* A clear and descriptive title.
* A detailed description of the problem.
* Steps to reproduce the bug.
* The expected behavior versus the actual behavior.
* Your operating system and Python version.

### Suggesting Enhancements

We welcome suggestions for new features, mechanisms, or business use cases (samples).
* Open an issue outlining your proposal.
* Describe the use case and why it would be beneficial for the DIR/ROA ecosystem.
* If proposing a new topology or core mechanism, please reference the relevant sections of the DIR architecture or ROA manifesto.

### Pull Requests

1. Fork the repository and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes (`pytest`).
5. Ensure your code complies with our linting rules (`ruff`).
6. Issue that pull request!

## Development Setup

### Prerequisites

* Python 3.12 or higher.

### Installation

Clone the repository and install it in editable mode with development dependencies:

```bash
git clone https://github.com/huka81/decision-intelligence-runtime.git
cd decision-intelligence-runtime
pip install -e ".[dev,eoam]"
```

### Running Tests

We use `pytest` for testing. To run the test suite:

```bash
pytest
```

### Linting and Formatting

We use `ruff` to ensure code quality and consistent formatting.

To check for linting errors:
```bash
ruff check src/ samples/ tests/
```

To automatically format your code:
```bash
ruff format src/ samples/ tests/
```

## Repository Structure

When contributing, please respect the separation of concerns in the repository:

* **`src/dir_core/`**: The core Kernel Space components (Decision Flow, JIT Validator, Context Store, Event Bus, etc.). This code must remain domain-agnostic.
* **`src/dir_core/utils/`**: Supporting utilities for samples (e.g., config loaders, LLM clients, mock generators) that are not part of the core DIR specification.
* **`samples/`**: Concrete implementations and use cases.
  * `01` to `29`: Foundational mechanisms and topologies (e.g., `00_quick_start`, `03_idempotency_guard`).
  * `31+`: Complete business use cases (e.g., `31_finance_trading`, `32_fraud_gate`).
* **`docs/`**: Architectural documentation, manifests, and system blueprints.

## Coding Guidelines

* **Type Hinting**: We heavily rely on Python type hints. Ensure all new functions and methods have proper signatures.
* **Kernel vs. User Space**: Maintain a strict boundary between what the Agent (User Space) does and what the Runtime enforces (Kernel Space).
* **Documentation**: Document complex logic, especially within `src/dir_core/`, as it serves as the reference implementation of the DIR architecture.
* **Sample Configuration**: Use `src/dir_core/utils/config_loader.py` for loading YAML configurations in new samples to maintain consistency.

## License

By contributing, you agree that your contributions will be licensed under its Apache 2.0 License.
