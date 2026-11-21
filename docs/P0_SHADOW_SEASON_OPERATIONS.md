# V3.3.13 Shadow season-operations contract (P0 DEPLOYMENT-002)

**Status:** PR candidate; not deployed. **Champion V3.3.12 remains frozen.** This document does not authorize a merge, workflow change, bet, or model promotion.

## Minimal path using existing code

The existing `hbi.collector_handoff` imports a provenance-authenticated original program into an **isolated CORE-003 SQLite only**, with original-byte SHA and full-field checks. PR #213 adds an explicit research-only status report for every handled race:

```text
Collector original archive -> existing CORE-003 importer
  -> immutable original roster -> shadow_records
  -> optional append-only shadow event JSONL -> local readback
  -> Pre-Watch research consumer (not yet deployed)
```

The transport includes race ID, roster, source hashes/timestamps, source/history/market status and blockers. It uses `betting.v33.evaluate` only if a complete external V3.3 case and all required original source, independent identity, and PIT attestation flags are present. The raw historical cohorts in this PR do **not** meet those requirements, so genuine cases must remain `NOT_RUN` / `BLOCKED`. No p(win), fair odds, minimum price, EV or BET can be inferred from the Collector status report.

## Manual isolated invocation (no production change)

```bash
python -m hbi.collector_handoff \
  --db /isolated/core003-pilot.sqlite \
  --collector-root /isolated/collector-original.zip \
  --collector-provenance /isolated/provenance.json \
  --source-report /isolated/core003-source-report.json \
  --out /isolated/collector-shadow-handoff.json \
  --shadow-log /isolated/collector-shadow-events.jsonl
```

Paths are illustrative, **not** claims these files exist in a runner. Omit `--shadow-log` for no event-log write. Import requires genuine authenticated provenance; a manually invented provenance receipt does not meet independent evidence standards. Never point at production SQLite or the frozen decision ledger.

## Planned daily and weekly checks — NOT enabled

Daily operator contract:
- Count physically discovered, original-byte authenticated, imported, `SOURCE_READY`, model-ready, fully assessed by actual Betting runtime and `BLOCKED` races *separately*.
- For every `SOURCE_READY` race, confirm exactly one transport terminal status and byte-backed append/readback. No `SUCCESS=NOOP`.
- Two **consecutive** runs with source-ready races but zero explained terminal assessments, or with missing logged results, mean `P0_COMPLETION_STALL_TWO_RUNS`. Known source/model/market blockers are explicit terminal reports, not silent zero completions and not valid betting assessments.
- A model/pit/market blocker remains `NO-GO`, not a workflow reliability incident on its own.
- Do not use later source observations for earlier decisions.

Weekly operator contract:
- Recalculate archive and report hashes, reconcile field counts, compare append-only event counts and readback, rerun original-source negatives and full `pytest -q` / `ruff check .` on exact HEAD.
- Do not promote `TMP-...` IDs or cross-provider joins by name.
- Compare research Shadow coverage without changing the Champion gates.

**Not implemented/authorized:** a scheduled daily/weekly checker, notifications, live Pre-Watch import, full-field WIN capture, model calibration, or production transport. Reuse existing schedules only under separate HQ approval. Season end is **unresolved**.

## Historical CI dependency found 2026-11-21

`ci.yml` step "Replay authenticated Collector originals through isolated SQLite model gate" requests `core003-pilot-state` from run `41518035718`. The GitHub run currently exposes `core003-pilot-report-41518035718` and `bet-mvp-shadow-41518035718` but not the state artifact. GitHub CLI returns `no artifact matches any of the names or patterns provided`. This is an **unavailable original prerequisite**, not a regression in the patch's Ruff/pytest. The required CI job must remain **FAIL** until an authenticated, immutable equivalent is supplied and the workflow is separately authorized to use it; do not skip the replay or fabricate bytes to turn the job green.

Other local original material: 21 Nov Collector ZIP SHA-256 `ddb07503641d88aec4f90ef263f0fdf322c8a8ed852c8ee28d8fec19e49ceff4`; CORE-003 SQLite SHA-256 `2aa5340f42d0566ec066e42a53d2f887a0e160153c8db239d8c552ee717a7960`. Four Jägersro original-byte SQLite readbacks previously verified. The Bjerke Oct20 ZIP has mismatching legacy receipts and must not count as a full authentic replay PASS.

## Rollback and adoption gates

No active schedule or `main` is changed. The immediate rollback is to close the draft PR and discard the branch. A later approved merge must first pass exact-head required checks and archived original-source replay with an accessible real artifact. Even after an approved merge, Shadow adoption requires **separate** explicit owner authorization, at least 14 days shadow-parallel observation and functional prewatch/health readback. This is not permission for automated wagers, promotion, or staking.

**Decision now:** SOURCE partial GO on verified original-byte subset; SHADOW LIMITED NO-GO; BETTING MODEL NO-GO.
