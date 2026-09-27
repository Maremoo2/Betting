# Research Observatory v1

Research Observatory is the monitoring layer for the frozen prospective shadow system.
It is intentionally separate from the probability model: observability may improve
without changing `FUNDAMENTAL_CHAMPION_V1_1`.

## Nightly sequence

After the 00:30 Europe/Oslo shadow settlement job restores the latest HBI state, it:

1. settles eligible shadow tickets;
2. fetches official winners for frozen T-4 decision runs that still lack an outcome;
3. materializes race-level predictive evaluations from the frozen decision-time
   distributions;
4. builds a data-health report;
5. builds predictive/economic summaries and calibration tables;
6. persists a research trend summary;
7. exports SQLite to CSV and JSON;
8. verifies SQLite integrity and writes SHA-256 hashes;
9. uploads a unique 90-day research backup;
10. uploads the rolling 30-day `hbi-state` used by the next scheduled job.

The unique backup artifact is named with the GitHub run ID, so a later run cannot
overwrite the earlier research snapshot.

## Frozen decision audit

Every first T-4 decision is now stored in `shadow_decision_runs`, including PASS and
NOT_EXECUTABLE outcomes. The row preserves:

- actual decision timestamp;
- race start timestamp;
- target and actual minutes-to-start;
- execution latency from ideal T-4;
- fundamental model version;
- frozen fundamental, market and combined distributions when available;
- model-market conflict;
- decision status/reason;
- number of paper tickets created.

A later five-minute watcher run cannot replace the first frozen T-4 decision for the
same race/product/shadow-policy target.

This is important because evaluating only bets would create selection bias. PASS and
NOT_EXECUTABLE races are part of the research population too.

## Data health

The daily health report includes:

- races discovered;
- race-field/starts coverage;
- Vinner market coverage;
- number of fundamental model runs and shadow-eligible runs;
- mean history coverage;
- active runner rows and known-history coverage;
- ATG runner coverage;
- provider fetch count/failures and failures by provider;
- T-4 decision status counts;
- T-4 latency mean/median/p95;
- paper-ticket and settlement coverage.

Missing values remain visible as missing. The report does not silently treat a missing
fundamental model, market snapshot or result as a successful observation.

## Predictive evaluation

Once an official winner is available, `race_research_evaluations` stores metrics for
the exact distributions frozen at decision time:

- fundamental log loss;
- market-only log loss;
- combined log loss;
- fundamental Brier;
- market-only Brier;
- combined Brier;
- model-market conflict;
- model versions and source market timestamp.

The report shows a separate sample size for fundamental, market and combined metrics.
This prevents a combined model with fewer eligible races from looking directly
comparable to a larger market-only sample without exposing the difference.

Calibration is reported in 10-percentage-point probability bins for the fundamental,
market and combined layers.

## Economic diagnostics

Shadow economics remain a separate evaluation layer:

- settled paper stake;
- net P/L;
- ROI on settled stake;
- mean CLV;
- positive-CLV rate.

P/L and CLV never replace proper probability scoring. A short profitable run is not a
promotion criterion.

## Trend summary

The Observatory groups all stored race evaluations by fundamental model version and
tracks the latest daily reports. This is designed for Champion/Challenger research
once a large untouched prospective sample exists.

No model is automatically promoted because a metric improves.

## Backup integrity

Every nightly research backup includes:

- `data/hbi.sqlite`;
- CSV exports of canonical tables;
- one complete JSON database export;
- nightly settlement report;
- Research Observatory JSON;
- Research Observatory Markdown;
- `backup-manifest.json`.

Before upload, HBI runs SQLite `PRAGMA integrity_check`. The manifest records file
size and SHA-256 for every included file plus GitHub repository, commit and run ID.

The workflow requests 90-day retention for immutable research backups. Repository or
organization retention policy may impose a lower platform maximum.
