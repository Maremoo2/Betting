# DATA-006 — five official past result rows (research only)

Source: immutable Collector run 42346290934. Klosterskogen 7 Nov prestart PDF SHA256 020eedb5bfb3f5cea0e2d55bac6622a01f3fe51a473c8a33bd9ecaa93c1f222a, observed 2026-11-07T06:18:01Z. Target physical race RIKSTOTO:KL_NR_2026-11-07:2; Tysvær Tjerand start #9, UELN 578001020230009. Independent UELN+pedigree DNT 2024 auction catalogue match remains PROVISIONAL_MATCH, not individual verified registry.

Five retrospective official DNT Jarlsberg result events matching the five prestart PDF history rows:
- June 4, 2026 race 8, start #3: DG gallop, 2100m Volte, Adrian Solberg Akselsen.
- July 3, 2026 race 1, start #4: unplaced, 31,4, 2100m Volte, same driver.
- August 7, 2026 race 7, start #5: fifth, 33,9, 2100m Volte.
- September 15, 2026 race 4, start #3: fifth, 34,8 g, 2100m Volte.
- October 16, 2026 race 7, start #4: fifth, 35,2 g, 2100m Volte.

Official result sources: https://old.travsport.no/Sport/Resultater/Jarlsberg-Travbane/?date=20260604 and same path for date=20260703, date=20260807, date=20260915, date=20261016.

Source limitation: independent official DNT web pages were *read on Nov 8 after the target*, with no retained original HTML/SHA or certified historical provider publication time. DNT result pages do not show the target UELN. Official event result match is not proof of permanent register identity or PIT. Research-only validator src/hbi/data006_historic_crosswalk.py and tests/test_data006_official_crosswalk.py implement fail-closed exact date/track/race/start/result checks and explicitly disallow model or betting authority.

Prior DATA-005 original 120-line stratified parser diagnostic: 824/840 correct or absent; 0 manual visual signatures on those 120. Both Holter and Tysvær five source lines on KL original page 2 have now been visually inspected separately. No extrapolation to 900 rows.

BENCHMARK-002 retrospective 2022–2024 5,274-race model comparison is already present at docs/benchmark002/WALK_FORWARD_BENCHMARK.md. Challenger V2 + terminal market log loss 1.5516082 vs calibrated terminal WIN 1.5569939 (paired delta -0.005386). Terminal WIN is not decision-time WIN. First30 reference: Champion 2.12908725 vs normalized same-freeze WIN 1.94910626, only 3 days and 0 PIT. There is no independent 2026 Challenger holdout for this task.

Frozen: CHAMPION_UNCHANGED=true; PREWATCH_V3_3_12_FROZEN=true; CHALLENGER_SHADOW_ONLY=true; PIT_HARDGATES_UNCHANGED=true; 2025_LOCKBOX_CLOSED=true; AUTO_BET=false; BET_AUTHORITY=false; AUTO_MERGE=false.
