# M7B.2a — historical identity and point-in-time feasibility

Research-only; no model admission. Recommendation: **M7B2_NEXT_RESEARCH**, with
**M7B2_HOLD for general integration**. Completion of this study is not approval
of features, retrospective training, p(win), M8, Champion or betting changes.

## Base and frozen cohort

HQ merged #49 at `dddbc003218c162efede77de45c495d437f80656`; this is the current
main/base checked at start, not an unmerged dependency. Reference #49 head is
`c77fd9952a0497efd1663ab76f86a3d3977f8bd8`. Read/reused M7A, M7A.1, M7B.1,
M7B.1a/b evidence, original PDF/official archives, M5/M6 identity/label/PIT
contracts. No original DATA-002/003 deliveries have become available; no new
search/backfill, new crawler or parser was created.

Frozen M7B.1b baseline: 90 original diagnostic observations, A90, quantitative B53,
C51, joint ABC33, 25 venue candidates and14 ambiguous. Baseline D/E0/model0.
The pipeline pins the original compact report SHA and reproduces it through
`history_quality.run` before proceeding. Known60 and locked30 remain unchanged;
these are diagnostic regression cohorts, not representative estimates or a fresh
holdout. Only the51 original C-pass observations are studied. The other39 are
explicitly NOT_EVALUATED for D/E, not declared failures or silently dropped from
the original90 denominator. Earlier reports and gates remain unchanged.

## Deterministic evidence pipeline

`python -m hbi.history_feasibility` reuses original source loaders, PDF field
routing, biography interpretation and the checked DNT/ATG historical reviewers.
No external request occurs during replay. Original manifest subsets were extracted
from **already available** release ZIPs, each checked against its documented
parent SHA and original PDF bytes. There were no new remote data requests.

`tests/fixtures/m7b2a-crawler-manifests-v1.zip` (18,063 bytes) contains three
unaltered crawler manifest byte streams and a hashed subset manifest. SHA256:
`e66bbb68234f45822ab26735f4d7bab4fcb9f5ba91ab494b0e8cad772828aee0`.
The original release ZIPs are not duplicated. Parent asset URLs, original member
paths, parent ZIP hashes and per-member hashes are in the subset manifest and
PIT ledger. Existing source bundles are reused, not recollected.

This evidence is the crawler's recorded acquisition plus release-archived bytes;
it is not an independently notarized timestamp or proof of earliest publication.
The original `PDF_OK` request includes exact PDF SHA, bytes, URL and `at_utc`:

| Document | Actual PDF download recorded by crawler | Parser captured_at (separate) |
|---|---|---|
| Bjerke/Eskilstuna20Oct | 19Oct18:20:49.764190 UTC | 19Oct18:20:50.386923 UTC |
| Solvalla/Åby21Oct | 19Oct20:22:15.333152 UTC | 19Oct20:22:16.198917 UTC |
| Jägersro24Oct | 19Oct18:22:18.335516 UTC | 19Oct18:22:19.517579 UTC |

Printed date alone is never availability proof. Each exact history row remains
bound to original PDF hash/page/line/horse block. Original market/prize columns
remain quarantined raw evidence and are not materialized as fundamental features.

## Identity study: D is a bounded retrospective research conclusion

All51 are **IDENTITY_VERIFIED** for this research chain; candidate/ambiguous/
conflict/not-found counts are0. This is not a global alias registry, stable-ID
availability before every target, life-cycle certification or provider admission.

- NO19: exact official registration is checked in archived canonical Rikstoto
  target starts and in the exact DNT historical result horse URI, date/race and
  venue/photofinish reference. The ledger retains original registration, PDF
  biography, original/historical names and every source hash. Registration numbers
  are not inferred from names or start numbers. Birth year is NOT_REPORTED where
  the checked source does not state it.
- SE32: exact target field of names/numbers **plus age, sex, sire/dam** links the
  original PDF horse to its ATG ID. The same stable ATG ID/pedigree is checked in
  the historical result. Target/historical field collisions fail closed. Swedish
  original TMP registrations stay intact; no cross-provider alias is invented.
  Case/punctuation variants are recorded, not fuzzy-matched. A substantive name
  change without additional documentation is a conflict requiring research.

Five source layers stay separate: PDF transcription, semantic output, official
historical result/conditions, identity evidence, and temporal availability. No
official value backfills the PDF semantic output. All18 incomplete B observations
are included in D coverage without relaxing any semantic exclusion.

## Physical historical race study: C

All51 chains identify one official physical race, representing **50 unique races**.
ALF MARTIN and STOLT ELMAR share the documented Bjerke1Sep race8; they are two
horse observations of one race, not a duplicate label for one horse. Other races
at the same venue receive distinct research IDs. The research ID hashes the
source-bound country, official venue identity, date and external race reference;
it is not a new provider ID or a date/number-only guess.

The race ledger separates printed reference, official external identifier and
research identifier, with original official conditions/results held separately.
For ATG, country, track ID/code, date, number, sport, unique result field, horse ID,
distance and start method are checked. For DNT, official venue/date/race heading,
registration row and dated photofinish reference are checked. Source format
omissions (including unreported scratch flags and NO actual historical clock)
stay NOT_REPORTED. No absence-of-scratch flag is manufactured. ATG naive race
clocks use the existing provider's Europe/Stockholm convention, explicitly
separate from publication/officialization; 19 NO historical exact clocks are
missing. Old historical dates are sufficiently earlier than all cutoffs without
inventing a midnight race time. Missing same-day clocks fail the study check.

## PIT scopes: PDF observation versus enriched research chain

Unknown for51/51: `result_official_at`, `source_published_at`, and earliest
availability to the provider. No fast-publication assumption is made. Actual
snapshot observations are known; an observed snapshot is a positive upper bound
on availability of those exact bytes, not an invented publication timestamp.

The audit reports two distinct scopes for each observation and cutoff:

1. **PDF_ONLY:** exact original PDF bytes observed by the crawler. All51 have
   positive before-cutoff observation proof in all four scenarios. For Custer's
   T-24h cutoff this is close: recorded19Oct18:20:49 UTC precedes18:25 UTC; no
   date-only shortcut was used. This proves observed excerpts, not identity or
   official-result availability and not semantic correctness of unknown codes.
2. **FULL_RESEARCH_CHAIN (Gate E here):** requires an as-of version for the PDF,
   official historical-result snapshot and target stable-identity proof. All
   required source roles must be hash/provenance-bound and observed **strictly
   before** cutoff. Late snapshots cannot be inserted into this locked chain.
   This is a conservative research gate, not a change of M5/M6 feature admission.

Late official verification is still permitted for **retrospective label research**
for all51 historical starts. We do **not** require a retrospective label to have
been fetched before the race it labels. We also do not infer that a PDF value was
unavailable merely because its independent check was fetched later. The two scopes
prevent confusing later verification with timely feature evidence. Whole-chain
`PIT_VIOLATION` below means using the **selected later snapshot** in a claimed
as-of decision would leak information; it does not prove earliest publication was
late or that the original PDF itself leaked.

## Scheduled cutoff study and actual output

The six physical targets are routed by their complete original field, including
combined-program races with the same printed number. Original PDF scheduled wall
clocks, not actual start/result times, define the research scenarios:

| Target | PDF schedule | Zone |
|---|---|---|
| Bjerke20Oct L4 | 20:25 | Europe/Oslo |
| Bjerke20Oct L6 | 21:07 | Europe/Oslo |
| Eskilstuna20Oct L7 | 20:36 | Europe/Stockholm |
| Eskilstuna20Oct L9 | 21:15 | Europe/Stockholm |
| Solvalla21Oct L9 | 21:26 | Europe/Stockholm |
| Jägersro24Oct L1 | 13:30 | Europe/Stockholm |

All are UTC+02 on these dates; IANA conversion rejects DST folds/gaps and supports
winter UTC+01 explicitly. Schedule heading pages are recorded separately from
horse-history pages: God Only Knows' race heading is page6 and horse history is
page7; this does not reproduce the reported split **horse-history block** bug.
Actual target-start times are NOT_REPORTED by this study and target results,
statistics, market values and equipment are never consumed.

| Minutes before scheduled start | PDF-only PIT verified | Whole-chain PIT verified | Whole-chain violation | ABC | ABC+D | ABC+D+E |
|---|---:|---:|---:|---:|---:|---:|
| 1440 | 51 | 18 | 33 | 33 | 33 | 9 |
| 60 | 51 | 18 | 33 | 33 | 33 | 9 |
| 15 | 51 | 18 | 33 | 33 | 33 | 9 |
| 4 | 51 | 18 | 33 | 33 | 33 | 9 |

Per scenario: PIT_DATE_ONLY0, PIT_INFERRED_UNAPPROVED0, PIT_UNKNOWN0 in the actual
51-chain cohort. Unknown publication/officialization timestamps remain unknown;
positive before-cutoff observed snapshots, not inferred publication, support the18.
There are **zero future historical events and zero contradictory identity/race
chains observed**, but33 selected whole-chain snapshot sets are too late and
are excluded. Negative tests cover missing times/sources and genuine future events.

The18 whole-chain passes are Jägersro24Oct histories with source controls observed
22/23Oct before even the23Oct11:30 UTC T-24h cutoff. As of this study23Oct,
**24Oct remains a scheduled future target**, not a completed empirical backtest.
These are source-availability scenarios, not claimed historical predictions,
a completed target outcome evaluation or a prospective model run.

Gate A51, B33 complete/18 explicit unknown, C51, research D51. A–D and ABC+D are
synonyms here (33); A–E and ABC+D+E are9. Counts never mix51 with the original90
or1,605 raw lines. Every record keeps all old exclusion reasons, including old
D/E NOT_APPROVED reasons, explicitly labelled as preserved baseline reasons.
New research gate results do not rewrite those historical decisions. General
`HISTORY_FEATURE_CONTRACT_NOT_VALIDATED` and model_eligible=false still apply to90/90.

## Selection and unresolved limitations

This C-selected diagnostic cohort favors existing corroborated source chains.
D finding51/51 does not estimate identity coverage in the other39 or archive.
NO19/19 and SE32/32 pass retrospective D, but whole-chain E retains NO0/19 versus
SE18/32 because of source retrieval chronology and target-date differences, not
better Swedish sport performance. Only Jägersro24Oct survives whole-chain E.

Quantitative B retains33 explicit AUTO cases, excludes all17 UNKNOWN methods and
one other incomplete case; no VOLT is inferred from absent a. D retains all six
DQ observations, but B retains none; E retains two of those six only as research
evidence. No qualification observation occurs in this51 subset (both original
qualifiers were outside C); this is **zero coverage**, not qualifier validation.
Gallop, raw result type, missing/numeric time, date/track and start-method group
counts are in GATE_REPORT. These exclusions could bias future complete-case
training toward selected venues, dates, formats and clean finishers. No archive-
wide bias estimate, training sample or performance claim is made.

Remaining: independent reviewer/identity life-cycle evidence, original official
publication/correction histories, broader qualifier/VOLT/result-code coverage,
source versions observed before historical cutoffs for more targets, validated
field-specific feature contract and full-field modelling/labels. Later modelling
would also require chronological OOS/baselines/calibration. Birth years and
cross-provider ID aliases must not be inferred without source documentation.
No human or blinded verification was performed; source replay/control is Codex
and deterministic validators, explicitly not fully independent human sign-off.

## Reproduce and inspect

Python3.12, existing project dev installation (`pip install -e '.[dev]'`), no new
dependency. Output directory must not exist; it cannot overwrite a locked run.

```sh
python -m hbi.history_feasibility --output-dir /tmp/m7b2a-new
python -m pytest -q tests/test_history_feasibility.py
python -m pytest -q
ruff check .
```

The CLI writes five versioned JSON files: identity ledger, physical race ledger,
PIT evidence, 204-row cutoff audit, and gate/selection report. Committed compact
JSON files equal actual output. Per-snapshot hashes/URLs/observation times and
original source lineage permit offline replay. Exact output hashes, local tests,
CI and head SHA are recorded in evidence and the Draft PR after actual execution.

Negative TEST_ONLY mutations cover same-name horses, changed names/IDs/pedigrees,
colliding fields, missing identity evidence, conflicting as-of versions, missing
provenance/clock, future events, late publication/observation, correction after
cutoff, DST/zone boundaries, multiple semantic/PIT exclusions, and false model
admission. Synthetic cases are software tests, never empirical study results.

No collector, old parser, known/holdout, existing strategy/model/PIT admission or
workflow is edited. Additive research files and an18KB source subset only.
Rollback: close/revert this Draft PR; there is no production state to restore.
