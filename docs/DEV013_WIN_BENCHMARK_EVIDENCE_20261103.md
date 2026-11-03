# DEV-013 | Deterministic pre-T−4 WIN benchmark reference

**P0 — read-only research.** Baseline main: `4047fdee0984b4289b1ef86797f894b8d0227da0`. PR #127 (DEV-012) was already merged. No PIT recovery, source admission, model, odds, strategy or wagering modifications.

## Reproduced root cause

DEV-011 successfully paginates cumulative GitHub originals but DEV-009 `read_archived_models()` previously selected the **earliest** `report_created_at_utc` per physical `race_id`, independent of whether a later legitimate pre-T−4 freeze existed. In the first post-merge scheduled CORE-003 run [41711979794](https://github.com/Maremoo2/Betting/actions/runs/41711979794) that yielded 59 distinct races, ten original-result-scored Champion/CORE-004 pairs, **zero** triple comparisons and zero PIT certificates.

For Eskilstuna race 8, original GitHub artifact [13230691299](https://github.com/Maremoo2/Betting/actions/runs/41635474321) has SHA-256 `d3036bc47fab25a5e1ca5b621fba6b0d340537b03f953449ab84400298a3b1d4`, frozen 12:25:23 UTC, 12/12 model runners, 0/12 WIN. Original artifact [13235845295](https://github.com/Maremoo2/Betting/actions/runs/41646155051) has SHA-256 `f04dd8f19254764114739009383371e3367c445c917c8fac5b08cf085e814a6d`, frozen **13:41:11 UTC** with 12/12 WIN observed **13:41:05 UTC**. Start was 13:46, so T−4 = **13:42 UTC**. Both are genuine SHA-index-attested frozen reports; the latter is not a post-cutoff injection.

Previously captured original official complete/raceday bytes (GitHub run 41662283155, artifact 13243490434) verify winner #5, 12 active, complete results SHA `0e779cd381b89c21d794394b8fc3bae4fb1bb94f8d9208028c03f936fad0782b` and raceday SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3a0b37e3d22bd4194b4e28e520d`. Expected same-freeze scores: Champion LL **2.81123044245**, CORE-004 LL **3.05005452040**, normalized WIN LL **1.80283699219**; multiclass Brier respectively **0.99837118864**, **1.04278005900**, **0.88940862546**.

## New deterministic rule and protections

1. Enumerate and SHA-verify all available original model files through the existing uncapped DEV-011 GitHub artifact inventory. An absent, expired, malformed or changed original remains blocked.
2. For each physical race, build the complete version history from available verified frozen originals. A model is eligible only when original `as_of <= report_created_at <= start_time - 4 min`, `MODEL_READY`, research-only, immutable, complete active field and complete Champion/CORE-004 vectors. **Do not inspect WIN presence, result, model loss, winner or payout during selection.**
3. Choose the **latest eligible pre-T−4** model timestamp. A SHA tie-breaker makes order independent of artifact download order. If no eligible model exists, retain a deterministic invalid record as `NOT_EVALUABLE`; do not manufacture a valid pair.
4. Evaluate WIN **only when all active horses have in-freeze Rikstoto WIN odds, one identical original observation timestamp no later than model `as_of`, valid field and odds**. No borrowing from other model versions or after-cutoff market.
5. Keep every available historical alternative (SHA, original source path, clock, eligibility/market completeness and selected flag) in the result record. One physical `race_id` still produces one score.
6. Previously SHA-verified official outcomes belong to the **physical race**, not one model SHA. Reusing identical original result bytes against a different frozen model requires rechecking the full active field, official start numbers, runner names, winner and dividends. Divergent official result SHA, altered or missing original receipts remain fail-closed.
7. No prior model/report/freeze/decision bytes change. PIT-003A and all hardgates are untouched. `bet_authority=false` and `stake_nok=null`.

**WIN raw SHA caveat:** Frozen model originals carry Rikstoto WIN odds and observation timestamps inside the SHA-256 verified original `shadow.json`. A *separate raw WIN HTTP response SHA* is not present for these ten original model reports and is intentionally recorded as `null`; the verified model-file SHA is not mislabeled as raw WIN-response SHA.

## Original-based ten-race audit (offline pre-merge)

The full machine-readable audit with complete original-model/result SHA, exact UTC clocks and T−4 cutoff is [DEV013_ORIGINAL_WIN_BENCHMARK_20261103.json](DEV013_ORIGINAL_WIN_BENCHMARK_20261103.json). It was derived from 64 available original model-artifact archives and their original cohort SHA manifests, plus original complete/raceday raw official result bytes in the scheduled scorecard artifact 13269145099.

| Physical race | Selected frozen SHA prefix | Active | WIN in selected freeze | Classification |
| --- | --- | ---: | ---: | --- |
| Eskilstuna 3 Nov #1 | `4853ed6bc8c7` | 12 | 12 | TRIPLE_EVALUABLE |
| Eskilstuna 3 Nov #3 | `9746b64fae5e` | 12 | 0 | MODEL_PAIR_ONLY — missing WIN |
| Eskilstuna 3 Nov #5 | `8cb3774ae965` | 12 | 12 | TRIPLE_EVALUABLE |
| Eskilstuna 3 Nov #6 | `9204bf13cf32` | 10 | 10 | TRIPLE_EVALUABLE |
| Eskilstuna 3 Nov #7 | `5a5a3a52fc73` | 8 | 8 | TRIPLE_EVALUABLE |
| Eskilstuna 3 Nov #8 | `f04dd8f19254` | 12 | 12 | TRIPLE_EVALUABLE |
| Jägersro 2 Nov #1 | `0e808867aca7` | 11 | 0 | MODEL_PAIR_ONLY — missing WIN |
| Jägersro 2 Nov #2 | `e415e5a5c4b8` | 9 | 9 | TRIPLE_EVALUABLE |
| Jägersro 2 Nov #3 | `cfa749bf1066` | 11 | 11 | TRIPLE_EVALUABLE |
| Jägersro 2 Nov #4 | `9a8f9c14b0f7` | 8 | 8 | TRIPLE_EVALUABLE |

**Before:** ten verified model/result pairs, zero triple market comparisons. **Expected after isolated original replay:** ten model/result pairs, eight triple comparisons, two model-pair-only, zero PIT certifications. These are **offline original-based coverage findings**, not a claim that the unmerged change has run in scheduled `main`. Neither pair-level averages nor a calibration/predictive ranking is justified by eight market comparisons.

The inherited cumulative inventory remains incomplete: five unavailable model artifacts and one distinct physical race (`RIKSTOTO:S2_NR_2026-11-03:8`) with conflicting official result original versions. Those must **not** be silently resolved by this PR.

## Acceptance

Run `ruff check .` and full `pytest -q`; CI must also run the genuinely original Eskilstuna two-freeze replay and upload its SHA/pinned-outcome evidence. Negative tests must prove later-but-invalid snapshots, after-cutoff WIN, missing market, incomplete field, changed model hash, conflicting result bytes, duplicate runs, PIT=0 and BET=false cannot manufacture an evaluation.

**No merge without explicit owner approval.** The first scheduled post-merge `main` CORE-003 scorecard (if a merge is approved) is the operational acceptance gate; PR CI alone cannot certify operation on main.
