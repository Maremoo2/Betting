# Horse Betting Intelligence

A Benter-first horse-racing research and decision-support system.

The project separates:

- a **market-free fundamental model**
- **race-difficulty / reject-option** diagnostics
- **static market probabilities**
- **market-path intelligence** across pre-race time states
- **model-market conflict / shrinkage**
- a calibrated **combined probability**
- price / EV / execution decisions
- frozen outcomes and calibration research

The system is deliberately conservative: AI/ML is used to improve data quality,
feature extraction, validation and automation. It does not replace the core
probability/market discipline.

## Data ownership

The HBI database is the canonical source of truth. The repository now contains a
SQLite persistence layer over `db/schema.sql`. Race cards, runners, immutable market
snapshots and frozen model predictions can be stored locally and later moved to a
server database without changing the modelling contract.

Google Sheets/Drive is intentionally treated as an optional dashboard/import-export
surface, **not** the primary database. A spreadsheet is useful for human review, but
it is a poor canonical store for high-frequency timestamped market snapshots and
frozen model history.

Provider-neutral interfaces in `src/hbi/ingestion.py` define how an approved ATG,
Rikstoto, exchange or other race/market feed can be connected later. No live data is
fabricated while those provider contracts are absent.

## Current V3.2 foundation

Implemented in this repository:

- point-in-time and source-provenance validation primitives
- normalized full-field market probabilities
- Benter-style second-stage probability-combination primitive
- separate race-difficulty / reject-option diagnostics
- timestamped market-path and material-change pre-watch logic
- structured review flags for material qualitative events
- persistent SQLite storage with idempotent snapshots and frozen predictions
- provider-neutral race/market ingestion contracts
- **market-only benchmark** for log-loss and Brier evaluation
- decision-price vs closing-price / CLV evaluation primitive
- Brier/log-loss/calibration helpers
- champion/challenger model governance
- SQLite-compatible canonical schema
- CI with Ruff + Pytest

See [ARCHITECTURE.md](ARCHITECTURE.md).

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

## Non-goals for the first foundation

The repository does **not** currently:

- place real-money bets
- scrape a provider without an explicit/approved integration
- let an LLM directly generate production p(win)
- treat odds shortening as automatic "smart money"
- promote new features because of one profitable backtest

External race/market data sources and scheduled live collection should be connected
only after their contracts, rate limits, timestamps and legal/technical access are
clear.

## Research rule

New features or models start as **challengers**. They can influence production only
after point-in-time, untouched out-of-sample evaluation shows incremental value over
the current champion **and the market-only baseline**. Hit rate alone is never a
promotion criterion.
