# MVP-014 | 4 November 2026 original source and coverage diagnosis

**P0, no BET, no PIT waiver, no re-frozen model, no historical backfill.**
Repository main checked 4 Nov before working: `254ae4b5ec6c5e97622a1881b581e9c7d9c86f9b`. DEV-013 #128 and multi-leg research #129 are both **MERGED**. This document is an append-only dated diagnostic; not a claim of operational PIT or main scorecard pass.

## 1. Current production research gate

- First two scheduled [CORE-003 41790102791](https://github.com/Maremoo2/Betting/actions/runs/41790102791) and [41791289072](https://github.com/Maremoo2/Betting/actions/runs/41791289072), 4 Nov 07:07 and 07:17 UTC, ran on above main SHA. The Oslo-hours schedule gate passed as a GitHub job but **every** actual capture, model, DEV-011 recovery and DEV-013 scorecard step was SKIPPED; zero scorecard artifacts. Do not count as operational DEV-013 verification. The workflow is still research-only. Check first subsequent *actually executed* scheduled run.
- Merge-base tests are GREEN; [main CI 41729859377](https://github.com/Maremoo2/Betting/actions/runs/41729859377) is PASS, but the authentic DEV-013 replay is intentionally PR-only and skipped on the main CI.
- Last actual cumulative scorecard on previous main is [run 41716853961](https://github.com/Maremoo2/Betting/actions/runs/41716853961), originals artifact 13269613642, coverage artifact 13269213750: **59 unique physical race IDs**, **10 original-result-scored Champion/CORE-004 pairs**, **0 valid simultaneous WIN triples**, **0 independently PIT certified**, 2692 GitHub inventory entries on 27 pages, 151 index-verified original artifacts, 10 original pinned results, and six source-blocked entries. DEV-013 original CI replay expects 8 valid triples for the controlled cohort, but this remains **not operationally confirmed on new main**.

## 2. Five supposedly missing model artifacts: real original-backed root cause

All FIVE are downloadable directly from GitHub today. They are **older legacy artifacts with frozen `shadow.json` but no `cohort-index.json`**, not expired GitHub bytes. The old DEV-011 `finalize()` bundles missing downloads and unmatched index format into the same `MISSING_OR_UNVERIFIABLE_ORIGINAL` category; thus its status was diagnostically ambiguous.

| GitHub run | Original artifact ID | SHA-256 of selected ORIGINAL model `shadow.json` | Original layouts |
| --- | --- | --- | --- |
| 41456642411 | 13147076977 | `9c4e0d2862ef1988a8babad2529a5f13ce3c896c10a857038d910a9cc187127b` | flat `shadow.json` |
| 41459303701 | 13147433634 | `3f01e5563c1d12c7ae3549e6e6e2c9753524d1d063b741b639e97cf9d2aa460f` | flat `shadow.json` |
| 41461113601 | 13149181358 | `380db85cbf812f52446a53492f41e88e9a6a8a823de4e2912f27e02e5f7b713b` | flat `shadow.json` |
| 41462919513 | 13150157261 | `c6317248eb9346b454ff0af99be607190e07e2b67aeb794a1aa4cf1887a78a13` | per-race original `<race_id>/shadow.json` |
| 41463276002 | 13150442459 | `acaa528c62854bb1514dc164f16bca0efff99f2c92f26bc191d012ccb5a41d62` | per-race original `<race_id>/shadow.json` |

These 5 artifact ZIPs contain **9** raw frozen model JSON files in total. Some legacy rows say `MODEL_READY`, but **there is no immutable original fixed-cohort index or per-report link contract**. No legacy model is promoted to scored prospective evidence merely because bytes exist.

**Minimal fix in this PR:** When an artifact's cohort index is missing but safe regular `shadow.json` source files are visibly present at that original run folder (flat or one-level per-race), return `UNINDEXED_LEGACY_MODEL_ORIGINAL` instead of `MISSING_OR_UNVERIFIABLE_ORIGINAL`. The existing `missing_originals` blocker list and `coverage_complete=false` remain; a missing download, symlink-only path, expired artifact, malformed cohort index or changed model hash remains blocked under existing codes. No scored, PIT-certified or BET-authorized race is added by this change.

Machine-readable post-change manifest distinguishes **5 present-but-unindexed legacy original artifacts + 1 conflicting official result race** rather than claiming five completely absent artifacts. This is truthful source-quality improvement, NOT an increase in qualified model coverage. Full CI and genuine five-source replay must pass before review.

## 3. New 4 November Collector originals: Jägersro PIT candidate

Collector [run 41784797103](https://github.com/Maremoo2/rikstoto-program-collector/actions/runs/41784797103), original archive artifact **13300048964**, observed `2026-11-04T06:21Z`:

- Original Jägersro physical meeting `S3_NR_2026-11-04`, full-field `MATCHED_AS_OF_SNAPSHOT`: 8 physical races, 84 starters, 82 active after two scratches. Startlist/PDF across all 8 physical races matched.
- **Race 5**: `RIKSTOTO:S3_NR_2026-11-04:5`, 20:30 Europe/Oslo planned start (T−4 20:26), nine total / nine active / zero scratched **at morning observation only**. `/starts` raw original acquired 06:21:01.630593Z, SHA-256 `fe1cde9c8642d8f526eb95c69c524c7b24243ba6669540f9126197e5ff4ea386`; original expanded PDF acquired 06:21:03.644626Z, SHA-256 `ddbe3bf9fe96dd04492509c184de9ae6491e9660f4f2772d2b8f07645eb74ba2`.
- **All 9 Rikstoto registration numbers are `TMP-S3-20261104-05-xx` placeholders.** This does not attest stable Sportinfo→ATG horse ID→Rikstoto cross-provider identity. It is an explicit **PIT identity source blocker until independently verified**, not grounds to assign identity by matching names.
- Across five *physical* collected meetings today, the archived active `/starts` fields contain 401 active starters (S2 100, S3 82, F1 125, F2 40, S1 54), all registration numbers `TMP` in the stored **Collector** original. Do not interpret as proof no other provider ever carries registered IDs.
- Collector source receipt metadata explicitly has `source_publication_time_attested=false`. Today's early source is a morning snapshot, not a prospective PIT T−4 source. The existing **4 Nov 22:15 Oslo** audit must be preserved with no duplicate task or backdating.

## 4. Separate V1 integrity audit on new main

[Real scheduled V1 system audit 41747967150](https://github.com/Maremoo2/Betting/actions/runs/41747967150) **FAIL** on stored state, original artifact **13284247086**:
- temporal `PASS`, 30 956 checked rows;
- provider `WARN`, 14 observed fetch failures (letrot 12, rikstoto 2);
- runtime replay `FAIL`, 353 compared / 539 skipped / **same five** historical mismatches;
- settlement `FAIL`, unresolved original ticket `a55a504a-bc34-487d-aced-75326dcb2b59`, Skive issue #82 context.
This is **separate** from green code CI and from current WIN benchmark; do not close, waive or rewrite historical V1 findings.

## 5. EV / multi-leg and deadline

The existing merged probability-only module can compute conditional full-system coverage for 4/7/8 qualified frozen physical legs; it is not a pool-pricing module. Bjerke/Axevalla V4X original key `X1_NR_2026-11-03#V4#4` with four physical legs remains verified **only at original meeting metadata level**; no complete SHA-verifiable contemporaneous V4X joint betting share, per-ticket price, takeout, jackpot amount and payout contract exists in this control. `system_ev=null`, `bet_authority=false`.

**Acceptance by 13 Nov:** A real eligible scheduled main CORE-003 scorecard demonstrating DEV-013 timing, SHA, unique race count, three-way WIN benchmark and failure diagnostics; independent verified cross-provider IDs + authoritative scratch semantics at true T−4 for at least one physical race; then future V4X data contract. The new legacy classification only prevents mistakenly calling extant but index-less originals 'missing'.

**Three priorities:** (1) first actually executed post-merge scorecard; (2) Jägersro 4 Nov T−4/22:15 independent PIT audit without time-leakage; (3) do not widen V4X EV until original complete joint pool economics are proved.
