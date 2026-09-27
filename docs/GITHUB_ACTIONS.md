# GitHub Actions PRE-WATCH runner

## Cadence

`.github/workflows/prewatch-hourly.yml` runs on a UTC cron that covers both CET
and CEST. The Python schedule gate converts current time to `Europe/Oslo`:

- 09:00 local: `MORNING_DISCOVERY`
- 10:00-21:59 local: `HOURLY_WATCH`
- outside the window: skip

This avoids hard-coding daylight-saving offsets.

GitHub scheduled workflows only execute from the repository's default branch.
The hourly schedule therefore becomes active after the workflow is merged to
`main`. Before that, the code can be reviewed in the feature PR.

## Persistent state on ephemeral runners

GitHub-hosted runners do not keep local files between runs. Each successful HBI run
uploads an artifact named `hbi-state` containing:

- `data/hbi.sqlite`
- `run-audit.json`
- CSV audit exports

At the next run, `hbi.state_artifact` restores the newest non-expired state before
the database is initialized/migrated. Artifacts are retained for 30 days. Because the
workflow normally runs every hour during the watch window, the latest state is
continuously refreshed.

For long-term production, a hosted PostgreSQL/object-store database is preferable.
The artifact mechanism is an intentionally simple GitHub-native first deployment.

## Data providers

The scheduler does not invent race data. If no live provider is connected, the run
finishes successfully as an audited `NOOP`.

A provider integration should create canonical race cards, timestamped market
snapshots and results, then set the canonical file paths for `hbi.scheduled_run`.
See `docs/DATA_CONTRACT.md`.

## Google Sheets mirror

Optional repository secrets:

- `HBI_SPREADSHEET_ID`
- `HBI_GOOGLE_CREDENTIALS_JSON`

If both are present, each successful run mirrors the canonical database into
`HBI_*` worksheets. These worksheets are for human inspection and do not become the
source of truth.

The service-account email represented by the JSON credential must have edit access
to the target spreadsheet.

## Safety

- no real-money execution
- no fake data when a provider is absent
- one workflow at a time via GitHub Actions concurrency
- state only advances on successful runs
- failed runs can upload diagnostics but do not replace the successful state artifact


## Nightly Research Observatory backup

The 00:30 Europe/Oslo settlement workflow also runs Research Observatory v1. It exports
the canonical database to CSV and JSON, verifies SQLite integrity, produces SHA-256
hashes, and uploads a unique artifact named
`hbi-research-backup-<github-run-id>` with requested 90-day retention.

The rolling `hbi-state` artifact remains separate and is still used for state
continuity between scheduled runs. Immutable research backups are for audit/recovery,
not as the normal state-restore source.


## V1 integrity artifacts

The nightly settlement workflow also produces `research-v1/` containing:

- `v1-system-audit.json` / `.md`
- deterministic research learning dataset JSON/CSV
- temporal-integrity status
- runtime replay-parity status
- settlement-integrity status
- Challenger forward-clock state

These files are included in the immutable nightly research backup.

The separate `HBI V1 Research Integrity` workflow runs the same engineering controls
against a clean database on PRs and main. NO_EVIDENCE is an accepted engineering state
for parity when no provenance-complete live decision exists yet; a mismatch is not.
