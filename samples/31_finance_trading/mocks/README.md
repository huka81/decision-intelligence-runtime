# Mocks — `31_finance_trading`

| Module | Role |
|--------|------|
| `llm_mock_strategy.py` | `make_mock_strategy()` for `setup_environment` when no live LLM is used. |
| `quote_generator.py` | Deterministic price ticks (`QuoteGenerator`) for OBSERVATION events. |
| `news_generator.py` | Synthetic headlines (`NewsGenerator`) for NEWS events. |
| `market_events.py` | `QuoteTick` and `NewsEvent` payload models. |
