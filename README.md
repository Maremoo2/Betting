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

Provider-neutral interfaces in `src/hbi/ingestion.py` remain the modelling boundary.
A read-only Rikstoto adapter is now implemented behind that boundary. Its endpoint
provenance is explicit: user-verified, open-source-observed, or historical-frontend
inferred. Provider failures are logged; missing values are never fabricated.

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
- read-only Rikstoto raceday + V/P/TV/T market collection
- point-in-time Rikstoto program fundamentals
- market-free `FUNDAMENTAL_CHAMPION_V1` shadow probabilities
- best-effort T-4 shadow watcher every five minutes
- immutable shadow ticket ledger and nightly settlement/report
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

The Rikstoto integration is read-only and intentionally contains no login, account,
purchase or real-money submission code. Historical/inferred endpoints are optional
and must fail closed when their contract is unavailable.

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


## Rikstoto shadow research

The repository now has a GitHub-native paper-betting loop:

```text
Rikstoto raceday discovery
  -> five-minute read-only market watcher
  -> early + best-effort T-4 snapshots
  -> V3.2 market/fundamental check
  -> immutable shadow BET / PASS / NOT_EXECUTABLE
  -> official result/final-odds settlement
  -> 00:30 Europe/Oslo daily review
```

The five-minute watcher runs through 23:59 Europe/Oslo so late races are not lost.
Every HBI workflow that writes the persistent SQLite artifact uses the shared
`hbi-state-writer` concurrency group, preventing two runs from restoring the same
old database and overwriting each other.

Automatic paper decisions currently start with **Vinner**. The watcher now captures
market-free pre-race horse history from the Rikstoto program and creates a frozen
`FUNDAMENTAL_CHAMPION_V1` full-field p(win) distribution before the T-4 value check.

V1 is a **shadow Champion**, not a validated production model: it uses only
empirical-Bayes-smoothed historical win records and requires at least 80% known history
coverage before the betting layer may simulate a ticket. Plass, Tvilling, Trippel and
multi-leg pool data are still collected without inventing product probabilities.

See [docs/RIKSTOTO_PROVIDER.md](docs/RIKSTOTO_PROVIDER.md) for endpoint provenance and
[docs/SHADOW_BETTING.md](docs/SHADOW_BETTING.md) for decision/settlement rules.


See [docs/FUNDAMENTAL_CHAMPION_V1.md](docs/FUNDAMENTAL_CHAMPION_V1.md) for the exact
market-free formula, point-in-time rules and promotion gate.
