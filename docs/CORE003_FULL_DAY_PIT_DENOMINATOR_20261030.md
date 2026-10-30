# CORE-001/002/003 – Full race-day denominator, immutable archival PIT audit

**Source:** archived Watcher [run 41111189754](https://github.com/Maremoo2/Betting/actions/runs/41111189754), artifact `hbi-state` ID **13003343590**, `data/hbi.sqlite` SHA-256 `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0`.

Research CLI: `scripts/core003_day_coverage_audit.py`, workflow `.github/workflows/core003-day-source-coverage.yml`. Runs *every* physical trotting race registered in the immutable DB between **27 and 30 October 2026**. It reads `races` and applies the existing stricter `core_pit_roster_verification.audit_race` to every race, without looking at winners, retrospective odds or selecting favorite tracks. Future races **before** T−4 remain in the denominator and are counted in a separate `FUTURE` category rather than misclassified as missing history.

Each day/country and day/track includes:
- total physical races, elapsed T−4 eligible, future races, raw source-ready, blocked, clock discrepancy counts and ordered blockers;
- per-race identity and exact archived observed payload SHA-256, not full raw provider payload;
- no future source interpolation, skipped-race backfill, cherry-picked winners, betting thresholds, true PIT certification or promotion.

**Critical limitation:** `core_pit_roster_verification` deliberately marks `pit_certified=false` when original independent provider publication and mutable historical schedule/roster revisions are unproven. A marked `raw_input_ready=true` is *not* PIT certification and cannot qualify CORE-001 or CORE-002 or train CORE-004.

The CLI SHA-checks the input archive before and after; it cannot overwrite the source DB and CI never uploads raw SQLite. CI assertions ensure every individual race appears once in day/country/track totals. This is technical **coverage observability**, not successful full PIT readiness.

**Signoff:** run pinned GitHub Actions, inspect output source hashes/country denominators; review independently before merge. Related [CORE #83](https://github.com/Maremoo2/Betting/issues/83), [CORE-001/002 #89](https://github.com/Maremoo2/Betting/issues/89), [CORE-004/P1 #90](https://github.com/Maremoo2/Betting/issues/90). No production writes, no changes to Champion/staking/odds or Watcher schedules.
