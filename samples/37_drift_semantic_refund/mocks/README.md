# mocks/

| Module | Role |
|--------|------|
| `llm_mock_strategy.py` | `make_mock_strategy()` for `setup_environment` when no live LLM is used. Refund decisions in the sample are simulated in `pipeline.py`, not via the LLM. |
