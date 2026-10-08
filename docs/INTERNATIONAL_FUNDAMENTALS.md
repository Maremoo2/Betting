# International fundamental ingestion — FULL_FIELD_ONLY_V1

This release expands read-only, paper/shadow ingestion. It does not add wagering,
change Champion v1.1 scoring, fit coefficients, or auto-promote a model.

## Runtime capability matrix

The packaged `src/hbi/provider_coverage.json` registry records reviewed capabilities.
An unknown combination is disabled. The registry is necessary but never sufficient:
every fetch must pass the full-field contract again.

| Country / discipline | Fundamental provider | Release status |
|---|---|---|
| Sweden / trot | ATG | Verified full-field, checked at every collection |
| Denmark / trot | ATG | Verified full-field, checked at every collection |
| Norway / trot | ATG | Verified where an exact ATG race and complete field exist |
| France / trot | ATG + LeTROT | Verified only with LeTROT corroboration for every active horse |
| France / gallop | France Galop | Disabled: public race field works, horse history redirects to sign-in |
| Finland / trot | ATG | Schema observed; no matching future Rikstoto field verified |
| Great Britain / gallop | ATG | No canonical future field; sample lifetime/year inconsistencies |
| South Africa / gallop | ATG | Schema observed; no matching future Rikstoto field verified |
| Norway / gallop, Sweden / gallop | ATG | Not full-field verified in this release |
| Switzerland, Spain, Hong Kong, USA, Canada | ATG candidates | No usable matched future field verified |

See the checked-in [live acceptance evidence](evidence/international-live-smoke-2026-09-29.json)
and [additional provider research](evidence/provider-research-2026-09-29.json).
These are dated observations, not blanket claims of coverage. A missing future race
is not proof that a provider never covers that country.

## Exact completeness contract

“Complete” here means the **career-summary contract** required by this ingestion:
explicit lifetime starts, wins, seconds, thirds and earnings, age, sex, trainer,
plus annual starts/earnings crosschecks and a safely matched canonical active field.
It does not claim an exhaustive row-by-row archive of every historical start.
Zeros must be explicit; missing values are not converted to zero. Counts must be
nonnegative integers, placings cannot exceed starts, earnings must be finite and
nonnegative, and lifetime totals cannot be below supplied annual totals. Provider
raw earnings units are preserved; they are not used in Champion win-rate scoring.

Rikstoto `/starts` and `/scratched` define the canonical active field. A failed or
malformed scratch response blocks enrichment. ATG calendar matching requires one
country/discipline/track/race-number candidate within five minutes of canonical
start. Both calendar and race payload must be upcoming. ATG's naive timestamps
are interpreted in Europe/Stockholm. Explicit track aliases cover Paris-Vincennes
and Øvrevoll; there is no fuzzy track matching or race-number guessing.

Within the verified race, each horse must have a unique normalized name **and the
same program number**. Numeric ATG horse IDs are not equated to Rikstoto registration
numbers: these are different namespaces. Both identifiers are recorded for audit.
Name collisions, changed numbers, unmatched horses, or any active-field difference
reject the entire race. Country suffixes are deliberately not silently stripped.
`match_confidence=1.0` means this deterministic identity contract passed; it is not
a statistically calibrated probability. An uncertain match has confidence zero.

France additionally requires an exact LeTROT meeting/race and field, matching
horse-page ID/name/year of birth, and identical career starts/wins for **every**
active horse. LeTROT's public embedded `horse-main :horse` fields `nbCourses` and
`nbVictoire` corroborate ATG, while ATG supplies the complete placings schema.
No claims are made that LeTROT's separate display statistic totals use the same
scope. LeTROT is not a standalone feature adapter. Any disagreement, authentication
redirect, HTTP failure, or missing embedded schema blocks the race. No credentials,
private endpoints, or access-control workarounds are used.

## Point-in-time and fail-closed behavior

- Observation/feature timestamps are the time all required responses completed,
  never the time a request was initiated. Provider publication time is null when
  unknown; the evidence explicitly records `FETCH_COMPLETED` as its basis.
- Final collection must still finish before the race. Watcher decision timestamps
  advance after collection. Replaying a prior cutoff cannot see later responses.
- Every attempt writes immutable `provider_payloads` evidence with category
  `FULL_FIELD_ONLY_V1`, including failures and per-runner reasons. No schema
  migration is needed; older databases receive normal existing migrations.
- All rows in an accepted active field must belong to the exact successful cohort.
  Mixed snapshots, missing evidence, probe-only evidence, and evidence older than
  ten minutes cannot enable shadow decisions. A newer failed attempt supersedes
  a prior success. Old canonical live data without this contract fails closed.
- The gate runs both before persisted model eligibility and at shadow decision
  entry. The model used for a live decision must match the accepted cohort.
  Frozen historical decisions remain immutable; this does not retroactively
  relabel them. Offline research fixtures keep their existing model semantics.
- The historical 80% research-model threshold does **not** override the live
  100% ingestion gate. An incomplete field receives no partial enrichment.

The fundamental snapshot is an explicit whitelist. Pool odds, betting percentages,
`lastFiveStarts.averageOdds`, editorial opinions, probable payouts, ranks, and
post-race results are excluded. Career inputs and gate metadata remain separate
from the existing market collector. Tests mutate market fields to prove feature
invariance.

## Verification and operations

```sh
pip install -e '.[dev]'
ruff check .
pytest -q
HBI_SMOKE_REQUIRED_COUNTRIES=SE,DK,NO,FR python -m hbi.live_smoke
python -m hbi.provider_research
```

The live-smoke workflow runs on relevant PRs, main pushes, and manual dispatch.
Acceptance requires actual future full-field runtime passes in all four named
countries; no-data is not counted as a pass. It probes up to three races per
meeting, at most 60 attempts, and writes every rejection and success. Additional
research probes public ATG calendars and official French pages without changing
the registry. JSON artifacts are uploaded even when acceptance fails.

Live racing availability and provider availability can make acceptance fail.
Do not lower the required-country list or mark no-data as passing to merge a
release. Run again when actual qualifying races exist. `UNVERIFIED` candidates
can be inspected in an isolated smoke database with `capability_probe=True`, but
probe evidence is explicitly forbidden from enabling runtime shadow execution.

To expand coverage, collect a real canonical future field, review the provider
schema and historical scope, add adversarial tests, retain dated evidence, then
review a registry change. The resolver, matrix and French corroborator are covered
by the protected-strategy workflow. There is no automatic country promotion.

SQLite connections now close at context exit, preventing live-smoke temporary
DB cleanup failures on Windows while preserving commit/rollback semantics.
