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


## CLI data flow

A complete local dry run can now be executed without any live provider:

```bash
hbi --db data/hbi.sqlite init-db
hbi --db data/hbi.sqlite import-races examples/races.json
hbi --db data/hbi.sqlite import-snapshots examples/snapshots.json \
  --race-start 2026-09-27T18:00:00+00:00 \
  --source-uri fixture://demo
hbi --db data/hbi.sqlite import-results examples/results.json
hbi --db data/hbi.sqlite export exports/ --format csv
```

When a real provider is connected, it should emit the same canonical objects rather
than changing the modelling/database layer.

### Optional Google Sheets mirror

Install the optional dependency:

```bash
pip install -e ".[sheets]"
```

Then use a Google service-account credential file:

```bash
hbi --db data/hbi.sqlite sync-sheets \
  --spreadsheet-id YOUR_SHEET_ID \
  --credentials /secure/path/service-account.json
```

The mirror writes to new worksheets prefixed with `HBI_` by default. It does not
overwrite an existing manually maintained `RACES`, `SNAPSHOTS` or
`BETS_OUTCOMES` worksheet.

See [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) for provider format and
[docs/RESEARCH_PROTOCOL.md](docs/RESEARCH_PROTOCOL.md) for model governance.


## GitHub-hosted hourly PRE-WATCH

The repository now includes `.github/workflows/prewatch-hourly.yml`.

After this workflow is merged to the default branch, GitHub Actions schedules the
same operating cadence as the current PRE-WATCH concept:

- 09:00 Europe/Oslo: `MORNING_DISCOVERY`
- hourly from 10:00 through 21:00 Europe/Oslo: `HOURLY_WATCH`

The workflow cron covers both CET and CEST and a Python timezone gate decides whether
the current run belongs in the Oslo watch window.

GitHub-hosted runners are ephemeral, so successful runs upload `data/hbi.sqlite` as
an `hbi-state` artifact. The following run restores the latest state before doing
new work. This gives the first GitHub-native persistent deployment without committing
the binary database to source control.

Until a live racing/market provider is configured, scheduled runs intentionally
finish as audited `NOOP` runs instead of creating fake race data. The scheduler and
persistence are therefore deployable before the provider layer.

See [docs/GITHUB_ACTIONS.md](docs/GITHUB_ACTIONS.md).
