# MVP-016 P0: transient GitHub pagination, authentic false-zero benchmark and safe status

**Read-only original diagnosis, 4 November 2026.** No model change, T-4/PIT relaxation, result backfill, retrospective re-scoring, portfolio or betting action.

## What failed in ordinary production research

[CORE-003 schedule 41817026855](https://github.com/Maremoo2/Betting/actions/runs/41817026855), job 126530254028, completed with GitHub `success`. During DEV-011 recovery, strict `hbi.dev011_coverage.plan()` correctly raised:

`ValueError: ARTIFACT_PAGINATION_CONCURRENT_CHANGE`

This means `total_count` changed between the pages of one GitHub Actions artifact inventory. It is a source-consistency failure; reducing the validation requirement would be unsafe. Workflow fallback emitted a manifest with no selected archives; unchanged DEV-009 then ran on an empty models directory and uploaded a valid-looking index with `physical_races=0`, `paired_champion_core004=0`, `triple_evaluable=0`, falsely suggesting that all cumulative evidence vanished.

| GitHub original | Artifact id | Original member SHA-256 | Meaning |
| --- | ---: | --- | --- |
| Broken source inventory fallback (run 41817026855) | 13315511779 | `b14c61c979c656e49da382d574f3416293303e582b3b864b646df592282c4ac7` | `missing_originals=[PAGINATED_GITHUB_INVENTORY_UNAVAILABLE]`, `selected_artifacts=[]`, NO inventory SHA |
| Misleading zero scorecard, same run | 13315945255 | `be7604e5b9604aa5439769e716038ad863854588fb6340b8333b4f77392e4481` | `0/0/0`, while source unavailable |
| Last healthy prior cumulative DEV-011 manifest, run 41814068321 | 13314445420 | `ecb4477a0ec5fc9c954862943ab8b39876d7b13c6adf701bf4e777eaa9f9df33` | 2950 GitHub entries across 30 pages, 181 recovered, nonempty verified inventory |
| Latest later valid cumulative scorecard, run 41817910059 | 13314644342 | Independently read/verified original in GitHub artifact | **64** physical races, **16** scored Champion-CORE004 model pairs, **14** WIN triples, zero PIT |

The later run 41817910059 has genuine cumulative source inventory: artifact 13314639321, 3030 entries / 31 pages / 189 recovered; source archive still incomplete, with five unindexed legacy model originals and one conflicting official result. The one-time 0/0/0 report was **not** evidence of losing the earlier physical-race cohort.

## Isolated safety fix

1. Try up to **three entirely fresh complete GitHub artifact pagination attempts**. Each retry starts from page 1 and removes only its temporary plan files. Retain strict DEV011 `total_count`, unique-artifact-ID, source branch, run-ID and original bytes validations; download and finalize original model/result files **only after** a complete consistent plan. Never splice partly read pages.
2. If inventory remains unavailable, write original `dev011-coverage/manifest.json` with explicit `PAGINATED_GITHUB_INVENTORY_UNAVAILABLE`; do not fabricate a GH inventory SHA or archived models.
3. Before DEV009, run a separate `hbi.mvp016_inventory_guard`. With source unavailable or corrupt manifest, publish `dev009-outcome-scorecards/source-unavailable.json`, **not** `index.json`; cumulative counts are `null`, `scorecard_generated=false`, and `prior_verified_scorecard_invalidated=false`. Emit GitHub `::error::` annotations rather than a silent green zero. Existing CORE003/PIT state is not touched.
4. If the inventory is verified, execute the **existing unchanged** DEV009 scorecard command. No new betting or PIT behavior.

## Exact regression contract

The PR's GitHub Actions CI downloads all three SHA-pinned original files: outage manifest, misleading zero scorecard, and successful previous manifest. It proves the source outage is detected, no zero-scorecard `index.json` is emitted, the status uses explicit `BLOCKED_SOURCE` and unknown counts, and a healthy manifest remains eligible. Synthetic negative tests cover changed schema, authority, unverified SHA, malformed file, missing source and bad source-contract types. The existing DEV011 pagination concurrent-change regression test remains in force. The CI replay performs **no new live market acquisition** and cannot certify PIT.

## What remains open

- Cumulative GitHub artifact retention, five unindexed older model archives and one official-result conflict remain `BLOCKED_SOURCE` / `BLOCKED_INFRASTRUCTURE`.
- Correct historical replay and settlement remain unapproved in the V1 system audit; Skive ticket #82 is not altered.
- Previously captured race models and scores remain unchanged. The genuine latest record **64/16/14/0 PIT** remains valid until superseded by a new complete original inventory; on failure, report **unknown**, never zero.
- Target: 13 Nov 2026 18:00 Oslo. Owner merge approval separately required. `bet_authority=false` throughout.
