# CLOUD-RUN-001 – Cloud source bridge (NO BET)

**Baseline:** V3.3.12 frozen. This PR adds only a manual, source-only byte readback. No new schedule, model change, SQLite write, alert, paid service or betting action.

## Verified GitHub evidence, 2026-11-12

- Collector `main` SHA `0d860759e8065f50e9fd9f3371fa22438cfca1fc`. Daily [run 43167334463](https://github.com/Maremoo2/rikstoto-program-collector/actions/runs/43167334463) succeeded; six program PDFs captured with `CAPTURED_UNVERIFIED`, and 30 NO/SE races / 321 runner entries in the source-only bridge. Not proof of complete daily coverage, fresh WIN, or model readiness.
- Collector draft Release id `442566649` stores the original ZIP and SHA-256 sidecar. Advertised archive SHA is `23871090f75ded32829fbc239ca6f1bae8be7d5784cc0f67c650a9aaeef639f3`, not independently downloaded/read back by this review.
- Betting `main` SHA `a3e9a36badd63bb9e625c77401f5bf6e2fe4e592`. Scheduled [PRE-WATCH run 43196941643](https://github.com/Maremoo2/Betting/actions/runs/43196941643) restored SQLite but logged `NOOP / NO_PROVIDER_CONFIGURED`. Green workflow is **not** a qualified prediction. Its `hbi-state` artifact was 252,235,934 bytes.
- `rikstoto-shadow-watcher.yml` defines a five-minute GitHub schedule and historical runs on November 10, but none were observed in the Nov 12 inventory checked. Windows remains owner for now. No second live watcher should be activated without HQ transition.
- Both repos are **public**. The Collector source Release is a **draft**, not an approved PIT original repository. Never place secrets or private WIN response bodies in Git.

## Owners and architecture

| Owner | Responsibility | Status |
| --- | --- | --- |
| Collector | Original daily calendar, programs/PDFs, startlist, source SHA and version | Implemented and running; coverage unverified |
| Betting HBI | Fundamental research, full-field probabilities, immutable decisions/results and PIT hardgates | Implemented; hourly scheduling is provider-NOOP |
| Windows watcher | Current actual five-minute capture and local WIN original archive | Keep unchanged during cloud pilot |
| CLOUD-RUN-001 | One manual, immutable-source ZIP/sidecar readback | This draft PR, no production scheduling |

The source-only readback takes one exact Collector release tag, downloads its existing ZIP and checksum, validates ZIP/manifest identity and original archive SHA twice, and outputs **RESEARCH_ONLY** with every PIT/BET flag false. This reuses the existing Collector capture and does not fetch any racing endpoint. It requires an HQ-approved read-only GitHub credential `CLOUD_RUN_COLLECTOR_READ_TOKEN` for the draft Release; absent secret or inaccessible draft fails closed. No secret is created in the PR.

## Actions use, schedules and costs

- GitHub inventory on November 12 through 10:24 UTC: **26 Betting run records** (21 CORE-003 source pilots, four PRE-WATCH, one system audit) and **one Collector daily run**. This is a real run count, **not** billable runner minutes or the monthly invoice. Job logs show PRE-WATCH runtime roughly 102 s; no complete month-wide billed total was accessible.
- Standard GitHub-hosted compute in public repositories: **$0** by the GitHub published 2026 policy. Artifact storage is separately subject to storage allowances and possible overage at approximately **$0.25/GB-month**; verify the account bill before adding more retention.
- A single hourly state upload is about **0.235 GiB**. At 13 uploads per day for 30 days, that would create about **91.6 GiB of uploaded artifacts** before expiry/deduplication. If all retained, steady-state hypothetical billable excess at $0.25/GiB-month is about **$22.8/month**. This is **not** an observed cost; cache, retention, actual cadence, and plan must be measured.
- GitHub `schedule` can be delayed or dropped, including near the top of an hour. It cannot guarantee real T−4. No external scheduler or paid storage has been authorized.

## Gates and acceptance

Even a passing real original ZIP check **does not** prove independent T−4 time, original live WIN, permanent full-field horse identity, scratched horses, calibration, official result join, or historical replay. Unit tests are synthetic and cannot satisfy live acceptance.

`COLLECTOR_SOURCE_READBACK=NOT_YET_LIVE_VERIFIED`

`LIVE_WIN_ORIGINAL=BLOCKED` | `T4_POSTCOMMIT=BLOCKED` | `PIT_PRIMARY=BLOCKED` | `AUTO_BET=false` | `AUTO_MERGE=false`

The historical `core003-pilot-state` replay artifact is still an independent unresolved gate; never weaken or rename it as PASS.

## One next owner action

Approve a read-only way to access the existing **draft Collector Release** without exposing credentials, then manually run the exact-source readback against `rikstoto-program-2026-11-12-20261112T062004681934Z`. Preserve the outcome as real-file evidence. Only after successful handoff should the separate cloud scheduling/storage transition be considered; leave Windows in charge until an independently verified owner handover.
