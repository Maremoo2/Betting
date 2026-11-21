# Betting V3 product candidate — PRODUCT COMPLETION-001

Status: development candidate in PR #213. Not deployed, not merged, NO BET.
Champion Pre-Watch V3.3.12 and all protected probability/decision rules remain unchanged.

## Existing pipeline and observable outputs

Use the existing Collector original archive and CORE-003 SQLite snapshot.
`hbi.prewatch_shadow_handoff --day` now inventories every SQLite race reference
and every physical race listed in the supplied day's Collector manifest. A missing
SQLite reference is retained as a blocked record. Composite products are explicitly
out of scope when the original manifest identifies them as such. Country/discipline
are retained; a discovered galopp race does not establish model support for galopp.

The command copies the immutable SQLite snapshot to its own output directory, checks
integrity, calls the existing `collector_handoff.verify_import` for each race, commits,
and produces one JSON day record with a Markdown view. The source database is rehashed
after execution. It makes no network requests and does not alter production state.
Every observation contains the original source report, hashes, start revisions when
verified, active field, model/market blockers and terminal transport status.
An explained terminal block is never counted as an assessed betting opportunity.

An authenticated original roster is now persisted before optional model-cohort
lookups. Previously MODEL_SOURCE_COHORT_NOT_FOUND aborted before original archival,
even after PDF/startlist/hash/day checks had succeeded. On the identical 21 Nov
snapshot, 25 additional diagnostic original rows survive this failure: source
readback goes from 4 to 29 races. Missing SQLite model fields/cohorts still block
research/model admission. No runner, history, identity or prediction is invented;
only ORIGINAL_PROGRAM_ROSTER_V1 provenance rows are appended.

```sh
python -m hbi.prewatch_shadow_handoff \
  --day YYYY-MM-DD --decision-time TIMEZONE_AWARE_ORIGINAL_ASOF \
  --db /isolated/original/core003-pilot.sqlite \
  --collector-root /isolated/original/collector-programs \
  --collector-provenance /isolated/original/github-source-provenance.json \
  --out /isolated/shadow/UNIQUE_RUN_DIRECTORY
```

These are configuration placeholders, not permission to collect or backdate data.
The provenance file records the authenticated Collector repository, successful
scheduled run and real run ID. A user-authored claim alone is not independent identity,
PIT, scratch or calibration evidence. Match all originals against independently
obtained artifact hashes before invocation. Keep original UTC and Europe/Oslo output.
`analysis_as_of_utc` belongs to the historical input; `observed_at_utc` is the actual
report execution time. All day-mode observations are explicitly offline replay.
They never become new prospective predictions.

## Status and authority mapping

| Existing evidence | Terminal day status | Betting assessment |
|---|---|---|
| Source missing/wrong archive day | SOURCE_UNAVAILABLE | NOT_RUN |
| Invalid clock, roster, hash or import | DATA_BLOCKED | NOT_RUN |
| Canonical start already passed at analysis as-of | ALREADY_STARTED | NOT_RUN |
| Authenticated imported source; no independent model/calibration admission | MODEL_BLOCKED | NOT_RUN |
| Original manifest says composite product | OUT_OF_SCOPE | NOT_RUN |

The pre-existing `evaluate_shadow_v33` is the only route to `betting.v33.evaluate`.
No transport derives BET/WATCH/PASS from source scores. Full-field intervals,
FFQ-1 case evidence, independent identity/PIT and qualified market inputs remain
required. The day-mode adapter does not synthesize these missing inputs, so it
cannot produce FULLY_ASSESSED or BET. Calibration status is MODEL_NOT_CALIBRATED.

## Logging, health and measurement

The run directory has one exclusive writer lock. A second writer fails closed.
Identical report retries are verified and idempotent; conflicting JSON or Markdown
cannot overwrite the frozen report. Use a new run directory for a changed observation.
If a writer crashes, preserve its incomplete files. Verify that no process still owns
that run before removing its stale lock; recover into a new directory and compare
original hashes. Never delete or truncate a historical log to recover operation.
The existing optional JSONL transport now uses binary append on Windows, preserving
exact bytes for its immediate SHA/readback check.

Supply earlier day records using repeated `--previous-report` arguments. Health
compares distinct, ordered observations against the complete inventory: two consecutive
unexplained missing/duplicate/unaccounted records emit P0_COMPLETION_STALL_TWO_RUNS.
Explained model/source blocks are accounted observations. Alert delivery remains
NOT_ACTIVATED: no SMTP, ChatGPT automation or production notification was configured.

Measurement reuses Research Observatory's PRIMARY_PIT_QUALIFIED population. Its
log loss, Brier, calibration bins, CLV, paper stake/P&L and ROI remain separate from
legacy/research diagnostic populations. The candidate adds race-count/standard-error
and descriptive normal-approximation intervals for prediction errors. These intervals
assume independent races, which may be false; they are not validation or profitability
claims. No observations means null metrics and NO_OBSERVATIONS, not a zero-loss model.
Existing Champion/CORE-004 paired research scoring remains in
`prospective_outcome_scorecard`; this adapter does not mix or retrain models.

## CI and historical source constraints

`scripts/github_retry.py` wraps only existing CI read commands. Transient API rate
limits/429/5xx/network resets receive at most three retries (1, 2, 4 seconds).
Permission-denied or missing artifacts fail immediately. Persistent errors remain
CI_ORIGINAL_SOURCE_UNAVAILABLE and nonzero, never PASS. Partial binary stdout from
failed attempts is discarded. Per-attempt timeout is bounded. Historical expected
hashes, baseline files, frozen tests and original replay requirements are unchanged.
No production workflow, event schedule, secret or paid service was changed.

RELEASE-002: within each CI runner, named downloads share one verified inventory per
source run and one ZIP per immutable artifact ID. Repeat steps rehash original bytes,
validate repository/run/ID and extract with readback into their own step directory.
Corrupt cache entries, ambiguous/expired artifacts, unsafe ZIP paths and conflicting
existing files fail closed, without silently redownloading over corrupt evidence.
GitHub artifact digests are checked when supplied; old original file pins remain
mandatory even if GitHub lacks its own ZIP digest. Cache is temporary within this
CI job, not a new permanent archive or substitute for expired originals.
All source queries retain contents:read/actions:read. No additional token rights
or secrets were created. Persistent installation-wide quota exhaustion is still
an external access failure; source caching cannot fabricate unavailable bytes.

The day command now calls the existing Betting runtime gate for every reference,
records its exact rejection, and writes a binary append-only event log. Exact
reruns verify that log rather than append duplicates. Source-ready blocks are
therefore traceable through runtime gate -> Shadow -> Pre-Watch -> log -> readback,
without claiming a fundamental model ran or qualified a wager. Local fault-injection
tests verify two-run stall flags and immutable alert delivery; these are labelled
software tests, not genuine outages or proof of full-day notification delivery.

The separately approved 21 Nov authentic rebaseline remains distinct from the missing
2 Nov state with SHA 60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0.
The latter is not recovered by a newer database. The original historical test is
retained unmodified. It must not be reported as a recovered old original.

## Operations, authorization and rollback

Implemented and locally tested does not mean activated. Existing Collector and
CORE-003 schedules continue unchanged. Under a later exact owner approval, attach
this command after an existing authenticated CORE-003 snapshot step, supply that
run's verified Collector archive, allocate a distinct isolated run directory,
publish JSON/Markdown and verify their SHA on a separate runner. Do not add a
competing schedule or mutate the comparator's logs/database. Test failure remains
visible even when a source outage blocks analysis. A full real day and delivery
of a controlled health alert remain separate acceptance requirements.

Weekly regression and calibration review are documented operator procedures, not
new active schedules: repeat exact-head Ruff/Pytest and original-source replay;
reconcile inventory/output hashes, duplicates and missing runs; review calibration
only for frozen qualified observations with official outcomes. No automatic
promotion, stake change or parameter update. Season end must be explicitly set by
the owner before activation; there is no invented date or automatic deletion.
Retain original artifacts under the existing approved retention; expiry still
blocks reproducibility and must not be hidden by shortening retention.

Rollback before merge: leave PR Draft and stop candidate invocations. No production
rollback is needed because none was activated. Tested data rollback: restore the
exact preserved SQLite bytes to a new isolated path, verify source SHA, migrations,
race/runner counts and integrity in a fresh process. Preserve all candidate outputs.
After a separately approved deployment, remove only the newly approved consumer
step and restore the recorded last-good commit/configuration; Champion remains
the fallback. No production rollback has been exercised in this delivery.

Final product decisions and exact-head test/CI/source evidence are delivered in
the single local BETTING_V3_PRODUCT_RELEASE_CANDIDATE package. Merge, activation,
source collection and qualified betting have separate decisions. Neither a green
test run nor an imported full field grants betting authority.
