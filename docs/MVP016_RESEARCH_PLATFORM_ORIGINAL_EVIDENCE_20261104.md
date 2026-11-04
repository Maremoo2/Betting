# MVP-016 – verified prospective research expansion | 4 November 2026

**This is an append-only source snapshot, not permission to change betting models or PIT.** Base `main` SHA `054dd26c5cfdaaf03219222ead25364b7a0ad915`. Due **13 Nov 2026 at 18:00 Europe/Oslo**. CI replays four exact original JSON bodies from [ordinary CORE-003 run 41814068321](https://github.com/Maremoo2/Betting/actions/runs/41814068321) with SHA-256. No model tuning, historical state edit, pool EV, or new PIT authority.

## Full cumulative audit – original 4 Nov ordinary run

| Original source | GitHub artifact | File SHA-256 |
| --- | --- | --- |
| DEV-013 scorecard | 13314117015 | `62b0d78ca75847d2f2bfe895af240e45eada96a7719aefe4f880c1da02cbe178` |
| CORE-003 source report | 13314296054 | `151168c074b7d1f0c92bb1c568f70bd23d2669a8903540a26c9b97f32121a7d7` |
| Original frozen cohort-index | 13313329016 | `3b804af346a340c6713b64319fd4201881040a264360e4a014069bb60c3e7cd0` |
| DEV-011 original manifest | 13314445420 | `ecb4477a0ec5fc9c954862943ab8b39876d7b13c6adf701bf4e777eaa9f9df33` |

Two **independent join assertions**: the cohort-index embeds the exact source report SHA; the cumulative scorecard inventory SHA equals the DEV-011 manifest inventory SHA. The original scorecard declares `model_originals_verified_by_sha=true` and `bet_authority=false`.

Cumulative physical races **59 → 63**, scored official-result Champion–CORE-004 pairs **16 → 16**, same-race Champion–CORE-004–WIN **14 → 14**, model pairs without WIN **2**, currently PIT certified **0**. Full model prediction fields **24/63**, *not* 24 official-result-valid races. Model pair original results **16**, 14 market triples. Calibration remains `INSUFFICIENT_DISTINCT_RACES` (minimum **30**). Closing-odds execution, actual ROI, and prospective V4X EV are **not established**.

The latest current CORE-003 *fixed cohort*, F2 physical races 3 and 4, contains 2 physical races, observed roster sizes 9 and 11, zero verified fundamental histories and zero complete time-consistent WIN markets. Both are blocked by source model admission: TMP original registration identifiers, no independent ATG IDs, incomplete ATG full-field and fundamentals. Neither produces a qualified model freeze.

## Transparent rejections (disjoint first-reason distribution)

| Existing scorecard original first blocker | Physical races |
| --- | ---: |
| `NO_VERIFIED_FROZEN_MODEL` | 25 |
| `FROZEN_FIELD_MISSING` | 8 |
| `CHAMPION_FULL_FIELD_INVALID` | 6 |
| `OFFICIAL_ACTIVE_FIELD_MISMATCH` | 4 |
| `OFFICIAL_FINISH_NOT_COMPLETE` | 3 |
| `CONFLICTING_OFFICIAL_RESULT_RECEIPTS` | 1 |
| **Total not evaluable** | **47** |

The above is a classification of **scorecard-record primary reasons**, not an independent root-cause reconstruction. Several races have additional secondary source blockers. Each physical race is counted once, never once per product or repeated workflow.

### Track coverage in cumulative original scorecard

| Track key | Physical races | Complete model fields | Scored model pairs | Triples |
| --- | ---: | ---: | ---: | ---: |
| BJ | 8 | 0 | 0 | 0 |
| F1 | 8 | 0 | 0 | 0 |
| F2 | 8 | 0 | 0 | 0 |
| F4 | 5 | 3 | 0 | 0 |
| OR | 8 | 0 | 0 | 0 |
| S1 | 8 | 6 | 6 | 5 |
| S2 | 14 | 11 | 6 | 6 |
| S3 | 4 | 4 | 4 | 3 |
| **Total** | **63** | **24** | **16** | **14** |

This is source-identity coverage, **not** a ranking or statement of the quality of any particular betting track.

## Actual implementation defects and delivery

### MVP-016 PR #132: false empty-cohort archive errors

Run 41796128435 original `bet-mvp-shadow/cohort-index.json` SHA `ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0` has explicit `original_cohort=[]`, `processed=[]`, `not_processed=[]`. The existing scorecard reader falsely reports `DECLARED_PHYSICAL_COHORT_INVALID`. The last main scorecard has 12 such source-index errors, mixed with genuine source limitations. The isolated proposed fix admits **zero** races, while contradictory nonempty lists still block. A standalone CI replay checks the original source bytes; the existing source and market hardgates remain intact.

### MVP-016 PR #133: automatically emitted join and paired uncertainty

Proposed source-only `hbi.mvp016_research_status` consumes existing original JSON files and produces one machine-readable `index.json`: actual per-race status/provenance, current CORE-003 source readiness and Collector blockers, primary and secondary rejection reasons, alternate model-freeze history, cumulative source gaps, per-day/track coverage, and same-race paired log-loss/Brier differences. SHA mismatches, changed denominator and false original results cause failure; no scoring or self-repair is performed.

The already existing scheduled CORE-003 workflow gets an isolated, **nonblocking diagnostic step** and independent artifact upload. If the source-join fails, it writes no false-success index and logs an explicit failure without changing the original state workflow. CI also runs the four-original replay from run 41814068321. Pairwise sample standard error is descriptive; no approximate confidence interval is emitted below the existing 30-distinct-race minimum. Any interval above that minimum still requires prospective independence assessment before inference. PIT and BET always remain false in this separate research report.

## Source-retention design – BLOCKED_INFRASTRUCTURE

Original model and scorecard outputs currently use GitHub Actions artifact retention (21 days); research-state SQLite is currently retained only 7 days; optional CI original replays use 30 days. Cumulative GitHub retrieval has verified 30 pages / 2950 original artifact inventory entries and 181 recovered artifacts. Five legacy model archive files are present but **unindexed**, not admissible; one official result for `RIKSTOTO:S2_NR_2026-11-03:8` conflicts. Cumulative `coverage_complete=false`.

A future retention extension must use an explicitly authorized, private immutable/object-locked destination with least-privilege read/write identities; append-only content-addressed SHA256 raw blobs, original GitHub run/receipt metadata, verified manifest signatures, readback/audit journal, encryption, defined retention period, access control, and a bounded error/failure protocol. No such new destination and authorization were verified in this work. **Do not implement external storage or invent a future PIT record.**

## PIT, integrity and multi-leg status

- Original Jägersro 4 Nov race `RIKSTOTO:S3_NR_2026-11-04:5`: morning 9/9 observed active but all registration numbers `TMP`. The existing 20:26 Oslo T−4 and 22:15 aftercheck remain authoritative; **0 PIT certified** at this morning control. Do not infer cross-provider identity from names. No duplicate automation.
- V1 original system audit [41796687537](https://github.com/Maremoo2/Betting/actions/runs/41796687537) **FAIL** on `main`: temporal PASS, runtime replay FAIL (five historical mismatches), settlement FAIL (Skive issue #82), provider WARN. Neither #132 nor #133 amends historical decisions or settles a ticket. Original outcome/coupon/price evidence for #82 remains unadjudicated.
- V4X 3 Nov: original multitrack pool `X1_NR_2026-11-03#V4#4`; physical legs `RIKSTOTO:S2_NR_2026-11-03:8`, `RIKSTOTO:BJ_NR_2026-11-03:7`, `RIKSTOTO:S2_NR_2026-11-03:9`, `RIKSTOTO:BJ_NR_2026-11-03:8`. Product/leg lineage is documented; original prospective joint pricing, complete model freezes, payout/takeout/jackpot contracts remain absent. Existing MVP-014 kernel remains **probability-only**. No V4X, V75 or V85 system-EV inference.

**Owner decision:** review isolated draft PRs #132 and #133; no merge without explicit user approval. Same existing Champion V1.1, CORE-004, V3.3.12, PIT-003A, T−4, thresholds and `bet_authority=false`. The 13 Nov deadline has not changed.
