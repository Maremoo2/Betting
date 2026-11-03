# DEV-012 — Original PDF continuation pages: strict field verification

**Baseline main:** `6fb794293243744f4071bcd031dae6786acc3adf`  
**Scope:** collector PDF field matching only. No model, odds, WIN, identity, scratch, PIT or BET gate modification. No historic backfill or betting.

## Original-based reproduction before fix

GitHub CORE-003 source run [41663427015](https://github.com/Maremoo2/Betting/actions/runs/41663427015); immutable artifact `pit003a-collector-evidence-41663427015`, id `13244810522`. Its original morning capture was recorded 2026-11-03 at 06:20:57 UTC (starts) and 06:20:59 UTC (PDF), both before the races' T-4 cutoffs. The Collector receipt's own `source_publication_time_attested` is **false**; this change does not elevate that field.

- Original `F1_NR_2026-11-03/full_program.pdf` SHA-256: `e565e0f797a74c7c82f7bf9e302d7b6a33a6433cea2334d5e093904f5447fb57`.
- Original `F1_NR_2026-11-03/starts.raw.json` SHA-256: `a4e4330ae9fc9279619333ecf55604c042021227a0bec0d3d69fd512b33eeea0`.
- Physical race 6: PDF page 9 has #1–12; continuation page 10 has #13 LADIVA DE PARIS and #14 LOVE TO RUN. All 14 match original starts; before fix, `COLLECTOR_PDF_FIELD_MISMATCH`.
- Physical race 7: page 11 has #1–12, page 12 #13 IMPERIAL DURABUTIN. All 13 match original starts; before fix, `COLLECTOR_PDF_FIELD_MISMATCH`.
- Physical race 8: page 13 has #1–12, page 14 #13–16. All 16 match original starts; before fix, `COLLECTOR_PDF_FIELD_MISMATCH`.

Reproduction: the existing function matched the unique heading page, then checked **every** original start against only that page's `get_text()`. Joining only the immediately following unheaded continuation page(s) makes missing-row counts 0, with no different number/name match.

## Minimal repair

`pdf_field` still requires exactly one original physical race heading, exactly one `START KL.` race clock, and all original start-number/name pairs. It now includes consecutive heading-free PDF continuation pages **only until the next recognized physical race heading**. Duplicated headings, missing names, mismatched names, a clock mismatch, and attempts to borrow a runner from the next race remain blocked. It does not approve ATG identity, mutable scratch state or PIT.

The isolated tests cover positive continuation, missing runner, next-race boundary, ambiguous duplicate race heading, missing clock, and an opt-in replay of both unmodified originals pinned by SHA-256. PR CI independently downloads the original immutable Collector archive and runs the replay.

## Scope of improvement

This removes the demonstrated false PDF-field rejection for **three unique French physical races** under the exact source versions above. It does **not** assert that these races now satisfy all other research, WIN, cross-provider identity, scratching, PIT or BET gates. In particular, French `TMP-` registrations and ATG availability remain independent checks. No historic run is modified; benefit requires future eligible original captures.

Bjerke 1 and 3 still have overlapping ATG full-field, retained-versus-live roster and SQLite-field conflicts; Bjerke 2 has unverified independent ATG identity. They are *not* repaired by this PR and should not be silently accepted.

**Merge requires explicit approval.**
