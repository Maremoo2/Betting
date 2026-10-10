# V3 validation run, 10 October 2026

PR #32 was already merged as fe00809ce5895b7ba65505b2ccd06906f94ee784
when this run checked GitHub. No second merge of that PR is required.

## Local work started

`research-local/next-steps-2026-10-10/jobs.py` runs two bounded local jobs:

- Live: 13 pre-registered races, 39 T−15/T−5/T−1 acquisition windows.
  HA Norway races 1–8; S2 Denmark first two races; S1 Sweden first two races;
  F1 France its discovered race 4. The first target is 10:55 Europe/Oslo;
  the last target is 15:14 Europe/Oslo. These are provider scheduled times.
- Historical backfill: 480 meetings across January–September containing V5A
  or old below-minimum market rejections. Previously cached envelopes are read
  without modification; new requests and V3 captures go to a separate directory.
  Combination endpoints are intentionally not requested by this targeted backfill.

No whole-year re-crawl, no changes to old frozen datasets, no betting execution.
Jobs continue as local Python processes and require this PC to remain running.

## Prospective registration

`live/registration.json` and `live/registration-lock.json` preserve the race
selection, original PRE-WINNER Engine v1 configuration/hash and unchanged tier
thresholds before the races. Each acquisition is sealed in `sealed-checkpoints/`
before later outcomes are opened. Signals are research only; PRIMARY requires
WIN/COL skew ≤60 seconds. Tiers use the existing exclusive AND classifier.

For a labelled acquisition all source fetches must start after the registered
target; completion must be within 60 seconds and before the scheduled start.
Changed scheduled starts, fetch errors and late acquisitions are rejected, not
reconstructed. Future provider updates cannot enter the signal register. Actual
race start is unverified, so this remains scheduled-start prospective research.
Provider update ages need review, and no ROI conclusion follows from collection.

## Progress and delivery

Paths under `research-local/next-steps-2026-10-10/`:

- `processes.json`: launched local process IDs.
- `live/progress.json`: next target and completed checkpoint count.
- `live/checkpoints.json`: capture/rejection records after observations begin.
- `live/prospective-pre-register.json`: immutable final register after all targets.
- `live/FINAL.json`: collection summary; manual quality review still required.
- `backfill/progress.json`, `backfill/reports.json`, `backfill/FINAL.json`.
- Both jobs create per-week ZIP files in their respective `weekly/` directories.

PRE/result separation is maintained: the controller never opens POST and never
merges code. A collection-complete marker is not a QC PASS. After collection,
review ZIP manifests/checksums, full-field coverage, source freshness, missing
windows and rejected observations before opening POST for this batch.

## Small collection API extension

`collect(..., race_numbers={...}, include_combinations=False)` limits endpoint
work to selected races/pools and labels deliberately skipped combination markets
NOT_REQUESTED. Existing commands retain their previous default behaviour.
This reduces irrelevant requests near T−1 and during targeted backfill.
