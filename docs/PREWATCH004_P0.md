# PREWATCH-004 P0 — original-backed Race Intelligence Packs (research only)

## Purpose and existing code reused

This PR is one bounded step, **not** implementation of Parallel Phase A.
It consumes the already verified [Collector -> Betting original archive importer](../src/hbi/cloud_run002_import.py),
which uses the existing [raw PDF + official starts SHA verifier](../src/hbi/collector_handoff.py).
It neither changes the Collector source parser nor modifies the frozen Champion or any production workflow.

Input: the exact immutable daily Collector ZIP named rikstoto-YYYY-MM-DD-RUN.zip plus its matching .zip.sha256.
It does not use release-note excerpts in place of original ZIP bytes.
A PR-only workflow pins the real 23 November 2026 Collector run
45141884691 for a source-based acceptance test.

Output: one JSON PREWATCH004_RACE_INTELLIGENCE_SOURCE_V1 per already-reconciled
physical NO/SE race, plus a source-discovered coverage manifest. All files are
write-once with exact byte readback, source-run and original SHA-256 lineage.
Unchanged reruns are allowed; same filename with changed bytes fails and requires
a **separate output directory**. Source revisions must never overwrite prior packs.

## What is confirmed and what is not

| Evidence | Output |
|---|---|
| Physical race + full official/PDF roster | Reuses cloud_run002_import.prepare_source and refuses conflicting fields |
| Race clock, distance, start method | From existing validated SourceRace, not reconstructed from release text |
| Official active/scratched membership | Exact as-of-source-capture, never claimed live |
| Program prior-starts | Exact derived raw-text lines, each SHA labelled, **not independent semantic gold** |
| Career performance/last 5 or 10/gallop/DQ rate | UNKNOWN until independent original-result evidence exists |
| Equipment/trainer/handicap extra distance | UNKNOWN where not independently admitted by this stage |
| Driver changes | Official starts driver included; **this stage does not certify effective driverChanges** |
| Previous Collector snapshot | Diagnostic differences only, no silent refresh of frozen outputs |
| Probability, odds, EV, A-WATCH, BET | Not generated; no market inputs or betting authority |

**Coverage denominators:** source_discovered_physical_races and listed_runners
are counts of verified-in-import Collector candidates. They are not evidence of
independent all-day calendar completeness, PIT attestation, or 100% available
race coverage. history_semantics_accepted is false throughout.

## DRAFT Phase A contract

A future parallel AI analyzer receives exactly one full-race pack.
Its output must be PREWATCH004_PHASE_A_DRAFT_V1, status DRAFT,
same race_id and source run, one descriptive assessment per **active** horse
with strengths, weaknesses and source evidence, plus race shape, candidate,
counterargument and uncertainty. The five **optional provisional** Champion
subscores are bounded at 25/20/30/15/10, not authorization.
Without validated evidence for a subscore, the AI should abstain; a syntactically
valid DRAFT does **not** establish sports quality. A separate finalizer must check
gates, exact start/roster revisions, qualified evidence, and genuine freeze time.

No AI API integration, cost, external API token, retraining, or new scheduler is
introduced. Neither the research/shadow Champion V1.1 nor CORE-003's
WIN/anti-favourite research output is promoted to V3.3.12 production scoring.

## Proposed deterministic Phase A finalizer + Sheets writer — NOT IMPLEMENTED

1. **Preflight:** fetch latest official starts/driverChanges receipts for the **same** source
   run, verify source times within 30 minutes at proposed real freeze, match
   all active horse IDs and official start; an older DRAFT has no freshness authority.
2. **Finalizer:** validate every active horse has evidence and full-sports explanation;
   require real prestart frozen_at and immutable assessment_id, five evidence-based
   subscores and 70-point rule including 15/10/18/8 component gates.
   No retroactive freeze, fabricated p(win), or post-result score changes.
3. **Writer preflight:** read *live* target sheet IDs, headers, actual blank rows,
   unique keys across the grid, and formula spill anchors. Treat the target workbook
   as mutable external state, never infer blank from API acknowledgement.
4. **Exact atomic write:** one updateCells batch to known empty rectangles in
   RaceAssessments and RaceFieldSnapshots. Never write formulas in RaceAssessments
   O:R, AD:AE, AG or RaceFieldSnapshots Q:S, U; never blind appendCells.
5. **Readback:** verify assessment row, all active horse rows, five numeric scores,
   FULL_RACE_QA, strict_roster_QA, STATUS_QA, score bounds, timestamp/uniqueness
   formulas, and a durable row in PreWatchWriteAudit. WRITE_CONFIRMED requires all.
6. **Recovery:** preserve original frozen JSON + source hashes on an independent
   immutable carrier when a write fails. Refuse duplicates; move misplaced rows
   only after inspecting actual keys. Never recompute a frozen analysis after start.

### Writer/finalizer acceptance scenarios for a later isolated test

- Good complete fresh prestart DRAFT -> fully confirmed freeze only after QA readback.
- Runner scratched after DRAFT -> requires reviewed rerun or documented exclusion.
- Added/deleted/duplicate runner, driver change, conflicting start -> no silent freeze.
- Old or mixed source receipts, unknown official race clock, after-start time -> BLOCK.
- Missing/unsupported evidence or out-of-bounds scores -> DRAFT/PARTIAL, no A-WATCH.
- Existing assessment key or changed body under same immutable ID -> no duplicate.
- Formula spill range and active populated tail rows -> no blind append.
- API ACK with unexpected target row or STATUS_QA=NO -> WRITE_UNCONFIRMED.
- Write audit missing or readback unavailable -> WRITE_UNCONFIRMED.
- Correct retry with identical frozen bytes -> idempotent; modified retry -> conflict.
- Network or downstream failure -> original untouched, no automatic BET.

The existing Pre-Watch production Ledger and scheduled ChatGPT automation are
**not** modified by this PR. Promoting any source pack or preliminary AI report
to FULLY_ASSESSED/WRITE_CONFIRMED is outside P0.

## Tests and limits

- pytest -q tests/test_prewatch004_pack.py
- PR-only genuine original archive E2E: .github/workflows/prewatch004-original-pr.yml
- Full existing PR CI: ruff check . and pytest -q

The P0 output cannot itself improve calibrated p(win) or the measured
positive expected value of any betting strategy. Those require separate
prospective evidence and held-out validation.
