# PREWATCH-004B3 — STRICT / FLEXIBLE pilot (NO BET)

This draft implements **only authentic cohort feasibility measurement**, not trained
prediction models. Parent PR #222 is draft/unmerged and itself depends on #221.

## Claims and limits

- STRICT requires independently attested complete last-five history plus PIT.
- FLEXIBLE would admit fewer than five starts only after permanent identity,
  exact official-original evidence and publication/observation before cutoff.
- Neither can admit Nov 23 history from the current certified source set.
- PDF row thresholds are diagnostic **research extraction workload**; they do
  not prove distinct races, past results, cross-provider horse identity, or PIT.
- Current verified Nov 23 source-only denominator is 26 races, 284 listed,
  275 active, 1,374 raw rows, 1,356 semantic research rows.
- 2026-10-20 seven authentic DNT starts are retrospective-only, not Nov 23 PIT.
- `NOT_ESTIMABLE` is mandatory for p(win), EV, Brier, log loss, ROI, and
  candidate BET counts until real independent time-bound historical sources,
  chronological training/validation/test cohorts and source-timestamped
  market prices exist. The output `research_bets_issued=0` is a safety
  fact, **not** an estimate that zero opportunities existed.
- This module does not change any Champion weights, model, strategy,
  production workflow, automation or Ledger.

## Next acceptance work

Obtain independently reviewed permanent cross-provider target IDs with
immutable original pre-cutoff receipts. Validate prior result documents
and complete-history index. Recover pre-frozen market odds as-of cutoffs.
Acquire enough chronologically separated full-field outcomes for meaningful
calibration. Only then implement honest STRICT vs FLEXIBLE predictive
models and compare error and risk-adjusted value on matched holdouts.

Run the PR-only workflow on exact HEAD, preserve source ZIP/SHA and
repeat/readback outputs. Existing MVP-018 artifact expiry is a separate CI
blocker; do not waive it or replace missing originals with test fixtures.
