# MVP-014 | BULK EXECUTION – source-grounded control, 3 November 2026

**Research-only. No production BET, model change, T-4/PIT waiver or historical backfill.** Original GitHub main at sprint start: `4047fdee0984b4289b1ef86797f894b8d0227da0`. Main unchanged in this documentation branch. Due 13 Nov 2026 18:00 Europe/Oslo.

## Status and prior work

- DEV-011 / PR #126 **merged**, cumulative GitHub original pagination and result receipt replay observed on main. [CORE-003 run 41716853961](https://github.com/Maremoo2/Betting/actions/runs/41716853961): **2692** GitHub entries on **27** pages; **151** recovered artifacts; 10 original-pinned result races; **five** unrecovered model archives and **one** conflicting official result race; `coverage_complete=false`.
- DEV-012 / PR #127 **merged**. Original multi-page French PDF full-field error repaired/tested. The new code also independently covers other original continuation-page patterns detailed below. **No post-merge scheduled source run containing those rejected races has yet been observed**; test-pass is not operational admission.
- DEV-013 / [draft PR #128](https://github.com/Maremoo2/Betting/pull/128) **CODE_COMPLETE / CI_PASS / NOT_MERGED**. HEAD `19f9eff2ea814ecce5b8013065e3728e52357dbd`. [CI 41721131733](https://github.com/Maremoo2/Betting/actions/runs/41721131733): Ruff PASS, 1504 passed / 78 skipped, original two-freeze Eskilstuna replay PASS; all four PR checks PASS. Read-only replay expects **10 model pairs, 8 same-freeze Champion/CORE-004/normalized WIN comparisons, 2 model-only, 0 PIT**. Operational main still follows earlier DEV-009 freeze selector and produces **10 model pairs / 0 triple**.
- First subsequent scheduled CORE-003 executions [41718391310](https://github.com/Maremoo2/Betting/actions/runs/41718391310) to [41725117632](https://github.com/Maremoo2/Betting/actions/runs/41725117632) report success but source/model/scorecard steps are SKIPPED by execution gate; they do not establish additional coverage.

## Prospective rejection matrix from ALL available source model indexes in defined window

**Exact window:** 3 November 2026 15:00–20:55 UTC, 41 completed CORE-003 runs with original `bet-mvp-shadow-<run_id>/cohort-index.json` artifacts, including scheduled runs and one push run. Repeated run mentions are deduplicated by physical `race_id`, *not* by product, pool or run ID. Raw proof remains in those GitHub Actions originals.

| Physical race_id suffix | Distinct run observations | Last observed active | ATG fundamentals / WIN at as-of | Outcome of original model ingestion |
| --- | ---: | ---: | --- | --- |
| F1 3 Nov #5 | 1 | 16 | 16/16 / incomplete | BLOCKED PDF continuation (five trailing runners); WIN also incomplete |
| F1 3 Nov #6 | 6 | 14 | 14/14 / complete | BLOCKED PDF continuation (two trailing runners); later corrected by DEV-012 |
| F1 3 Nov #7 | 10 | 13 | 0/13 / incomplete | BLOCKED PDF continuation; independent ATG/market missing |
| F1 3 Nov #8 | 9 | 16 | 0/16 / incomplete | BLOCKED PDF continuation; independent ATG/market missing |
| BJ 3 Nov #1 | 10 | 7 | 0/7 / incomplete | BLOCKED ATG full field + roster revision/identity |
| BJ 3 Nov #2 | 9 | 9 | 9/9 / complete | BLOCKED cross-provider identity |
| BJ 3 Nov #3 | 10 | 5 | 0/5 / incomplete | BLOCKED ATG full field + roster revision/identity |
| BJ 3 Nov #4 | 9 | 6 | 6/6 / complete | BLOCKED cross-provider identity |
| BJ 3 Nov #5 | 10 | 11 | 11/11 / complete | BLOCKED Collector retained/live roster revision + cross-provider identity |
| S2 3 Nov #7 | 9 | 13 | 13/13 / complete | BLOCKED PDF continuation (three trailing runners), DEV-012 same code path |
| BJ 3 Nov #6 | 9 | 13 | 0/13 / incomplete | BLOCKED PDF continuation (two trailing runners), plus underlying ATG |
| S2 3 Nov #8 | 9 | 11 | 11/11 / complete | MODEL_READY in eight runs, one earlier source exclusion; no PIT, source result conflict separately |
| BJ 3 Nov #7 | 10 | 7 | 0/7 / incomplete | BLOCKED original start-clock contradiction + ATG |
| S2 3 Nov #9 | 9 | 11 | 11/11 / complete | MODEL_READY in nine runs; no PIT |
| BJ 3 Nov #8 | 9 | 9 | 9/9 / complete | BLOCKED Collector retained/live roster revision + cross-provider identity |
| S2 3 Nov #10 | 9 | 9 | 9/9 / complete | BLOCKED TMP / roster / full-field identity contradiction |

**Distinct physical races: 16; research-model-frozen races: 2; blocked before model freeze: 14; independent PIT: 0.** These are cohort-specific counts, not the entire cumulative 59-race denominator. A `MODEL_READY` source report remains unapproved for PIT/BET where independent identification and strykestatus are missing.

### Original PDF reproduction across meetings

Original Collector artifact [13263866875](https://github.com/Maremoo2/Betting/actions/runs/41703256187) contains immutable PDF and /starts:
- F1 PDF SHA `e565e0f797a74c7c82f7bf9e302d7b6a33a6433cea2334d5e093904f5447fb57` and /starts SHA `a4e4330ae9fc9279619333ecf55604c042021227a0bec0d3d69fd512b33eeea0`.
- S2 PDF SHA `1c6d9a487ca381c73efbefa00d3664f75bb2392dd72b02912ce9fefffb8fc898`; /starts SHA `8dc8b0acbe405e483cfbe6f90272321be01d69864889e1ed2ef6d173fe85545c`.
- BJ PDF SHA `47f2eb2fb4823ed2e25b607b642f89487477ef1eced7076e69a5d9e85b91617a`; /starts SHA `05489dd37b32ddf7d9bace37c9824c175daaf5bfc56b0dd47fe79ccad273b951`.

Comparing first physical PDF page against correct heading-free continuation page (the existing DEV-012 parser) resolves trailing start-number/name mismatches in **F1 #5 (five), F1 #6 (two), F1 #7 (one), F1 #8 (four), S2 #7 (three), BJ #6 (two)**. This is original PDF *field* verification, NOT complete model admission/PIT. BJ #7 is a **separate source time conflict**: PDF 21:09 Oslo versus canonical race start 21:12; CORE-003 uses conservative earlier start with 180-second difference. Do not alter this clock gate.

## Cumulative original result coverage (unchanged main)

- [Run 41711979794](https://github.com/Maremoo2/Betting/actions/runs/41711979794): 59 physical race IDs, 10 official result+Champion/CORE004 pairs, 0 same-freeze triple WIN; 0 PIT; original result races pinned 0. Incomplete original coverage.
- [Last nonempty run 41716853961](https://github.com/Maremoo2/Betting/actions/runs/41716853961): **same 59 / 10 / 0 / 0**, but 10 valid original result receipts successfully pinned and checked, 2692 cumulative inventory entries. No new scored race in this comparison.
- Missing model artifact source runs: 41456642411, 41459303701, 41461113601, 41462919513, 41463276002. Original result conflict `RIKSTOTO:S2_NR_2026-11-03:8`. No synthetic recovery.
- Multiple market/fundamental timestamps and unknown prestart quote/closing-market availability prohibit economic ROI. Model log-loss/Brier and predictive calibration must remain separate from observed/quoted betting prices. No calibration conclusion from the ten-race sample.
- DEV-013 changes selection of the latest eligible pre-T-4 model original, independent of outcome and embedded WIN completeness; only a future ordinary main run after owner-approved merge may certify operational triple coverage.

## E – November 3 Bjerke/Axevalla V4X original

Original Collector run 41703256187, artifact 13263866875, raw `/api/racedays` **06:20:06 UTC**:
- Original discovery response SHA-256: `5f44e2ed8e01674b4e30dac4c14429aede5f39524685b836c4cff34bb3aaa1d6`.
- Provider composite `poolKey = X1_NR_2026-11-03#V4#4`, metadata `multiTrackRaceDayName = Bjerke/Axevalla`, `hasJackpot=true`. Bjerke and Axevalla meeting entries also declare companion pool keys. Actual `races` map S2#8, BJ#7, S2#9, BJ#8 in that sequence.
- Corresponding distinct physical IDs: `RIKSTOTO:S2_NR_2026-11-03:8` (11 morning active); `RIKSTOTO:BJ_NR_2026-11-03:7` (7); `RIKSTOTO:S2_NR_2026-11-03:9` (11); `RIKSTOTO:BJ_NR_2026-11-03:8` (11 in morning /starts but 9 in later CORE-003 readiness). This is an explicit field revision risk; later observation does not revise the morning original.
- This **does not** contain a complete original four-leg prospective collective snapshot, nor certified unit/fee, jackpot allocation, turnover, official combination-dividend contract or original coupon. Prior chat's 147 NOK coupon and 4,922 NOK payout are **not independently SHA-verified from this Collector archive**. The two BJ legs lack qualified model freezes. No valid V4X EV calculation.
- The existing pre-winner crawler deliberately excludes multitrack/secondary products from its full collective-gate. Research feasibility for regular V4/V65/V75/V85 does not automatically grant V4X contract completeness.
- Probability-only proposed module is separate from PR #128, market-independent, assumes independence, uses SHA-verified eligible original model reports and returns physical-race uniqueness, probability and row count. No payout, EV, ticket, PIT or BET authority. Product identity must be independently source verified.

## PIT and risk gates

- Existing Jägersro audit for `RIKSTOTO:S3_NR_2026-11-04:5` remains scheduled **4 Nov 22:15 Europe/Oslo**. No run now or duplicate. Current PIT certification count **0**.
- Continue to preserve separate five legacy V1 replay mismatches, [Skive #82](https://github.com/Maremoo2/Betting/issues/82), five missing model archive originals, the conflicting `S2#8` official result and lack of authoritative scratch semantics.
- `bet_authority=false`, no model coefficient, policy threshold, stake rule, PIT-003A or production decision was changed.

## Roadmap against 13 Nov 18:00 Oslo

| Deliverable | Code/CI | Real ordinary main / original outcome | Acceptance |
| --- | --- | --- | --- |
| DEV-009 | Merged/CI PASS | 10 scored model/result pairs in latest cumulative original scorecard | DONE technical; benchmark scope limited |
| DEV-010/PIT | Merged/CI PASS | No independently PIT-certified physical race | BLOCKED_SOURCE |
| DEV-011 | Merged/CI PASS | 27-page cumulative pagination, 10 pinned outcomes, six unresolved source cases | PARTIAL coverage, operating |
| DEV-012 | Merged/CI PASS | Original PDF continuation verifies six races; no new post-merge model admission observed | PARTIAL operational |
| DEV-013 | Draft PR #128, CI PASS | Eligible eight triples in original replay, zero on current main | BLOCKED_IMPLEMENTATION pending owner merge |
| DEV-014 / MVP-014 P1 | Read-only V4X metadata found, pure probability contract possible | 4-leg pool odds/ticket/dividends not verified | BLOCKED_SOURCE for EV |
| MVP-011 | Existing once-only audit | Pending Nov 4 actual T−4 | NOT_STARTED/PIT_NOT_CERTIFIED |
| MVP-012 / MVP-013 | Model provenance improved; reader/original scores verified | 59 cumulative races, ten model pairs; no PIT | PARTIAL |
| MVP-014 | This independent control/audit | 16 observed physical races in defined window; two model-ready | PARTIAL |

**Prioritized next actions (maximum three):** (1) Owner review of PR #128; on approved merge verify next actual ordinary CORE-003 with original scoring; (2) retain Jägersro 4 Nov T−4 and 22:15 original PIT audit; (3) independently source-certify multitrack V4X pool economics *after* P0 gates, never manufacture EV from WIN or marginal pool percentages.
