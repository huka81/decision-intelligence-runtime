# mocks — sample 36

| Module | Role |
|--------|------|
| `llm_mock_strategy.py` | `make_mock_strategy()` — deterministic JSON for ROA Explain and Policy prompts; no network calls. |

All business logic stays in `pipeline.py` and `dim.py`; this package is for test doubles only.
