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

## RELEASE-003 frozen operational acceptance

Baseline:816c6e9f9c3677e8db6a2ea2d2df3957dd4201cb, four required checks passed,
2260 tests passed. No model, decision, source policy or active schedule is changed
in this acceptance round. Additional tests inject adapter, write/readback, provenance,
source-binding and HTTP429 failures. They are software fault tests, not live events.

The existing CORE-003 workflow has an explicitly opt-in branch-only manual test:
`workflow_dispatch`, non-main ref, `execute=true`, `shadow_acceptance=true`.
Its concurrency group is unique to the test run; main retains the original literal
`core003-isolated-source-pilot` group. It restores main's immutable source snapshot
read-only into its own hosted runner, performs the existing bounded source capture,
then calls the existing day handoff into RUNNER_TEMP. Main-private archive writes
remain main-only. Source/output artifact IDs belong to this branch/run, so the
main-filtered production restore does not consume them. This probe is labelled
MANUAL_DISPATCH_PARTIAL_NOT_SCHEDULED_FULL_DAY and cannot satisfy full-day acceptance.
It creates no automatic schedule and cannot activate on main, even after a merge.
The bounded manual source probe explicitly excludes the unrelated all-history
outcome-recovery job. That step is NOT_TESTED by this probe, not passed or replaced;
mandatory CI outcome replays remain unchanged. Other branch outcome jobs have their
own run-specific group, while main retains its original outcome concurrency group.
The first probe was cancelled after its source artifact was verified because this
second concurrency boundary was found to be shared. Preserve the cancelled attempt
and its artifacts; it is not a successful complete workflow or a full-day test.

Isolated rollback is tested by stopping only a probe-created Shadow PID while its
own writer lock is held, preserving original SQLite and all frozen report/log bytes,
then resuming and repeating the same command. A stale isolated lock is removed only
after that exact PID has exited. Log line counts and SHA must remain identical.
This does not measure real Champion uptime or perform a production rollback.

### P0 closeout (scope is explicit; no false issue closure)

| Work item | State | Evidence / remaining function | Existing owner |
|---|---|---|---|
| DATA-003 / DATA-004 independent semantic gold | BLOCKED | Development diagnostics exist; issue104 still requires two independent readings and adjudication of390 fields | Source reviewers / HQ |
| CORE-003 source software | DONE | Existing capture/state plus authenticated21 Nov replay; not independent PIT readiness | Betting DEV |
| CORE-003 PIT readiness, issue83 | BLOCKED | Immutable multi-day full-field source/identity/time acceptance remains outstanding | Betting DEV / source owners |
| Collector-handoff archival transport | DONE |29 verified imports;39 diagnostic fields /409 entries; immutable log readback | Betting DEV / Collector |
| INTEGRATION archived source-to-Shadow | DONE | Existing CI authentic E2E with correct Betting-port rejection | Betting DEV |
| DEPLOYMENT-001 / DEPLOYMENT-002 | SUPERSEDED | Candidate work consolidated into213; operational activation not done | Betting DEV / HQ |
| PRODUCT COMPLETION-001 / RELEASE-002 technical deliverables | DONE | Frozen baseline CI/artifact/rollback/measurement evidence | Betting DEV |
| PRODUCT COMPLETION-001 / RELEASE-002 operational acceptance | BLOCKED | Carried into this single RELEASE-003 full-day gate, not declared complete | HQ / operations |
| PR212 | SUPERSEDED | Closed unmerged; transport and tests consolidated into213 | Betting DEV |
| Pre-Watch reliability, issue46 | BLOCKED | Frozen Champion/Sheets reliability acceptance is not replaced by Shadow archive tests | Betting DEV / HQ |
| PR213 merge / production / betting | BLOCKED | Actual full-day observation and separate owner decisions required | HQ |

Issues46,83 and104 remain open: their acceptance is not met. No new issue, PR,
model or parallel status system is created. The one remaining operational gate is
an actually observed, isolated automatic full racing day with this candidate code;
if the observation period has not occurred, report NOT_OBSERVED, never GO.


### RELEASE-003 one-off timed acceptance, 22 November

The existing branch-only source workflow can dispatch its own isolated probes at
frozen five-minute times on 22 November. Three finite standard Linux jobs keep each
job below GitHub's six-hour limit. This is opt-in, bound to the exact PR SHA, and
never runs on main. Moving the branch stops dispatch. Missed observations are
recorded and never backfilled. Each probe preserves its planned time separately
from actual source/adapter execution. The original 52-race Collector inventory
(run 44993097051, artifact 14742578389) is frozen in research/. All later discovered
physical races remain visible. The day is NOT accepted merely because dispatch
succeeds; completed artifacts, every race status, integrity and elapsed real time
must be checked after the last event. Clock receipts confer no PIT/BET authority.
No active automation, main schedule, production SQLite or model weights change.
