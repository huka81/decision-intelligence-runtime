# 10 - EOAM Live Simulation (Topology A with Quote and News Generators)

**Goal:** Demonstrate **Topology A (Event-Oriented Agent Mesh)** with a live-like simulation: quote stream, market news events, news scoring, and dynamic creation of position agents.

**DIR Alignment:** DIR Topologies §2 (EOAM), §2.1–2.4 (choreography, routing, priority preemption)

## Concepts Demonstrated

| Concept | Implementation |
|---------|-----------------|
| **Quote stream** | `QuoteGenerator` (dir) yields ticks: price, volatility, trend, volume; compatible with MARKET_SIGNAL / OBSERVATION payload |
| **News events** | `NewsGenerator` (dir) yields news with headline, sentiment, category, instruments_affected, raw_score |
| **News scoring** | `score_news()` in generator; `NewsScoringAgent` subscribes to NEWS, emits NEWS_QUALIFIED when score above threshold |
| **Reactive agents** | Instrument agents (OPEN_POSITION / HOLD), Position agents (CLOSE / TAKE_PROFIT / ADJUST_STOP / HOLD), NewsScoring (NEWS_QUALIFIED) |
| **Priority arbitration** | RISK_ALERT > CLOSE > TAKE_PROFIT > OPEN_POSITION > NEWS_QUALIFIED > HOLD |
| **DIM** | `dir.dim.validate(winner)` before execution |
| **Dynamic agents** | On ACCEPT for OPEN_POSITION, orchestrator spawns and registers a new `ReactivePositionAgent` |

## Flow

1. **Quotes:** Each tick is published as OBSERVATION with scope = instrument. All instrument and position agents subscribed to that instrument react and may emit policy proposals.
2. **News:** Every N ticks, one news event is published as NEWS. NewsScoringAgent scores it and may emit NEWS_QUALIFIED.
3. **Arbitration:** Orchestrator selects the winning proposal by priority.
4. **Validation:** DIM validates the winner (stub accepts all).
5. **Execution:** Mock execution; if winner is OPEN_POSITION, a new PositionAgent is spawned and registered for future observations.

## How to run

From repo root:

```bash
pip install -e .
python samples/10_eoam_live_simulation/run.py
```

## Configuration (in run.py)

- `INSTRUMENTS`: list of symbols (e.g. BTC-USD, ETH-USD)
- `SIMULATION_TICKS`: number of quote ticks to run
- `TICK_INTERVAL_SEC`: sleep between ticks (0 = no sleep)
- `NEWS_EVERY_N_TICKS`: emit one news event every N ticks
- `MAX_NEWS_EVENTS`: cap on news events
- `NEWS_SCORE_THRESHOLD`: minimum raw_score for NewsScoringAgent to emit NEWS_QUALIFIED
- `QUOTE_SEED` / `NEWS_SEED`: for reproducible runs

## Expected output

- Logs per tick: observation dispatch, agent proposals, arbitration winner, DIM result, mock execution or spawn.
- Summary: tick count, news count, number of position agents spawned, bus event count.

## Generators (dir package)

- **QuoteGenerator** (`dir.quote_generator`): multiplicative random walk in price; `next_tick()`, `ticks()`, `ticks_no_sleep(n)`.
- **NewsGenerator** (`dir.news_generator`): template-based headlines, sentiment, category, `score_news()`; `next_news()`, `news_events()`, `news_payloads()`.

In production, scoring could be LLM/RAG-based; here it is rule-based for determinism and no API keys.
