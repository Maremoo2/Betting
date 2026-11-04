# MVP-018 | Original-backed freeze rejection audit – 27 physical races

**Baseline:** [ordinary CORE-003 run 41826490000](https://github.com/Maremoo2/Betting/actions/runs/41826490000), original DEV-013 scorecard artifact `13320200641`, `index.json` SHA-256 `a7cc16d026ea08e0042dc4d6c5c2d75d3212bfd5fb00203dbbbbc36455f11d2b`. Its immutable denominator is **65** distinct physical races, 16 official-result-model pairs, 14 same-freeze normalized WIN triples, 0 PIT, **27** NO_VERIFIED_FROZEN_MODEL rows. This is a **historical baseline**, not the latest 66-race main run. Code never reconstructs or backdates a freeze.

## Original-based classification (latest observed matching source index per physical race)

The original research source `cohort-index.json` and its SHA were independently read from GitHub Actions archives. Every one of these **27** races had at least one original `original_cohort` membership and a matching `not_processed` record. The latest matching original CORE-003 source report SHA was also read for **all 27**; morning Rikstoto `/starts` and program PDFs were read from authenticated Collector original artifacts `13226634593` (3 Nov) / `13320555495` (4 Nov). SHA-pinned race-level evidence and actual source clocks are available in the generated original audit.

| Fysisk race_id (RIKSTOTO:) | Original CORE-003-run / original cohort SHA prefix | First effective source blocker | ATG verified active history | T−4 WIN |
|---|---|---|---:|---|
| BJ_NR_2026-11-03:1 | 41688477740 / `966fae062008` | ROSTER | 0/7 | No |
| BJ_NR_2026-11-03:2 | 41689647527 / `ff60ace9f57c` | ID | 9/9 | Yes |
| BJ_NR_2026-11-03:3 | 41695134468 / `484dbb677367` | ROSTER | 0/5 | No |
| BJ_NR_2026-11-03:4 | 41697599198 / `4f6afeb9194e` | ID | 6/6 | Yes |
| BJ_NR_2026-11-03:5 | 41702060001 / `a88a65bedf97` | ROSTER | 11/11 | Yes |
| BJ_NR_2026-11-03:6 | 41704777271 / `8551a8f0ee92` | PDF | 0/13 | No |
| BJ_NR_2026-11-03:7 | 41708503913 / `592543dcebc2` | CLOCK | 0/7 | No |
| BJ_NR_2026-11-03:8 | 41710594697 / `5cc2a0d920e4` | ROSTER | 9/9 | Yes |
| F1_NR_2026-11-03:1 | 41638113026 / `1eb636d66f54` | PDF | 17/17 | Yes |
| F1_NR_2026-11-03:2 | 41643813249 / `3dc1ae012ba7` | PDF | 0/15 | No |
| F1_NR_2026-11-03:3 | 41646155051 / `fa87f4f0f3f1` | ATG | 0/11 | No |
| F1_NR_2026-11-03:4 | 41650764835 / `978a2726e6ba` | ATG | 0/10 | No |
| F1_NR_2026-11-03:5 | 41659359660 / `032321d534f7` | PDF | 16/16 | No |
| F1_NR_2026-11-03:6 | 41665938596 / `a371cfd49e21` | PDF | 14/14 | Yes |
| F1_NR_2026-11-03:7 | 41672871572 / `d8efc561715c` | PDF | 0/13 | No |
| F1_NR_2026-11-03:8 | 41678644159 / `c3c6c1842da8` | PDF | 0/16 | No |
| F1_NR_2026-11-04:1 | 41826490000 / `87e8cd9751a9` | T−4 | 0/15 | No |
| F1_NR_2026-11-04:2 | 41826525357 / `912ef7d3cce4` | ID | 12/12 | No |
| F2_NR_2026-11-03:4 | 41627179906 / `e9a119a54c15` | ATG | 0/10 | No |
| F2_NR_2026-11-04:1 | 41803904316 / `256099892f61` | ATG | 0/7 | No |
| F2_NR_2026-11-04:2 | 41811192493 / `afb2f64cccba` | ATG | 0/13 | No |
| F2_NR_2026-11-04:3 | 41814068321 / `3b804af346a3` | ATG | 0/9 | No |
| F2_NR_2026-11-04:4 | 41814068321 / `3b804af346a3` | ATG | 0/11 | No |
| S1_NR_2026-11-03:2 | 41628334884 / `9c6f3b4c7db0` | PDF | 14/14 | Yes |
| S1_NR_2026-11-03:4 | 41633505763 / `4575f4c1c7e9` | ROSTER | 11/11 | Yes |
| S2_NR_2026-11-03:10 | 41711979794 / `535e9020ed7f` | ROSTER | 9/9 | Yes |
| S2_NR_2026-11-03:7 | 41703256187 / `b0aee1eacb1d` | PDF | 13/13 | Yes |

**Definitions:** PDF = original run `COLLECTOR_PDF_FIELD_MISMATCH` (9). ATG = original `COLLECTOR_ATG_ATG_FULL_FIELD_GATE_NOT_PASSED` or `COLLECTOR_ATG_FUNDAMENTAL_COHORT_NOT_COMPLETE` (7). ROSTER = active-set, retained/live roster-revision or SQLite full-field conflict (6). ID = independent identity/registration unverified even when fundamental field complete (3). CLOCK = original PDF start-time conflict (1). T−4 = freeze execution was already at/after the **conservative** cutoff (1). Grouping is a diagnostic classification, not a waiver of secondary independent blockers.

These map to normalized request categories: `SOURCE_CONFLICT=16` (PDF9 + ROSTER6 + CLOCK1); `MODEL_GATE_REJECTED=8` (ATG7 + T−4 1); `IDENTITY_NOT_VERIFIED=3`. Source original **WIN complete 10/27**, original **fundamentals complete 12/27**, and no race was automatically made eligible.

## Independent PDF original recheck

A read-only extraction of the original PDF and `/starts` bytes from both 3 Nov and 4 Nov compared program headings, unique physical race delimiters, exact start-number/name and clock. **All nine historical PDF-field blocker races now match the unchanged 3 November morning originals with the current parser's explicit continuation-page/header rules**. This corroborates prior merged DEV-012/#131 fixes **only for the PDF stage**. A complete per-meeting check identified **74/89** race sections matching those exact rules. The other 15 were composite/alternate physical-source sections in X1 and S5, not grounds to relax name or race identity. No historical model has been rerun or promoted.

For the nine old PDF cases, this is **retrospective code regression evidence only**, not a prospective post-fix freeze. Other source gates and actual T−4 could still block. An earlier source may be valid and yet a later official roster/scratch revision cause legitimate conflicting fields. Source observations, publication-time uncertainty, independent ATG registration, and authoritative scratch semantics remain separate.

## Execution funnel and intervention

**Observed historical funnel:** 27 original physical race IDs **discovered/selected** → 27 original fixed-cohort attempts → 27 original `not_processed` decisions → 0 accepted archived model-frozen reports for these 27 → 0 new result pairs → 0 new WIN triples → 0 PIT. There is no evidence that scheduling alone accounts for any of these 27; raising task count would not remove the tested source blockers.

A generic prospective funnel needs separate source-by-stage original observations. The new `mvp018_freeze_provenance.py` research tool explicitly reports **UNKNOWN** for a race not covered by the supplied archive sample, even when the cumulative scorecard says `NO_VERIFIED_FROZEN_MODEL`. It uses SHA-pinned immutable source bytes, refuses duplicate cohorts/changed SHA/broken membership, chooses the latest *observed source-rejection* by source clock (never by result, WIN or economic value), and cannot read as a valid model or certify PIT.

**Real software fixes already merged:** DEV-012/#131 PDF processing and MVP-016 #132/#134/#133 cumulative research intake and reporting. **New prospective model-eligibility fixes proven in this audit: 0.** The remaining ID, ATG, roster and T−4 categories require **new independent original source/clock evidence**, not a score change or invented registration mapping. The code in this research PR is diagnostic only; the original 65-race baseline and newer 66-race main observation are preserved separately.

No additional GitHub scheduled automation; no new model coefficient, champion/core weights, betting hardgate, PIT-003A rule, historical report or `bet_authority=false` changed.


## Independent full-field and outcome cross-check (ordinary 67-race original; 4 Nov 12:48 UTC)

This second baseline is [run 41832416078](https://github.com/Maremoo2/Betting/actions/runs/41832416078), original scorecard artifact **13324990108**, raw `index.json` SHA256 **a4a667bd596bde42b9e3dbed6d96247731067fe76f82b33ea816194fa68b5ff7**. It contains 67 distinct race IDs, 24 complete original frozen full fields, 16 scored independent official-result pairs, 14 WIN triples, 0 archive errors and 0 PIT. This update does NOT reclassify the original 27-race historical sample above: later two F1 source-blocked races produce 29 NO_VERIFIED_FROZEN_MODEL entries in the 67-race denominator.

| Original blocked group | Specific physical race IDs | Independently observed source status |
| --- | --- | --- |
| 6 `CHAMPION_FULL_FIELD_INVALID` | F2 3 Nov #1/#2/#3, F4 2 Nov #4/#7, OR 2 Nov #1 | All six original prestart `shadow.json` documents are `MODEL_BLOCKED` with `champion_p_sum=null`, `core004_p_sum=null`, source ATG full-field/fundamental rejection. F2 #1/#2/#3 and OR #1 also flag provider race or active-field identity conflict; F4 #4/#7 flag provider race identity/time |
| 8 `FROZEN_FIELD_MISSING` | OR 2 Nov #2–#8 (seven); S2 2 Nov #7 (one) | All eight original `MODEL_BLOCKED` documents contain `active_runners=0`, empty `runners=[]`, and explicit `NO_CANONICAL_ROSTER` / `NO_FUNDAMENTAL_COHORT_AS_OF`. A blocked frozen-file existence is not a valid full-field probability distribution |
| 4 `OFFICIAL_ACTIVE_FIELD_MISMATCH` | S2 2 Nov #1/#2/#4; S2 3 Nov #9 | Independently verified pre-T4 frozen scratch flags and post-race explicit `place=0, kmTime=Str` official rows. Existing code falsely compares only active p(win) members to all published rows. Dedicated draft [PR #138](https://github.com/Maremoo2/Betting/pull/138) original-replays exactly four and preserves stable frozen number, name, prestart scratch and outcome checks. Expected 16→20 scored / 14→18 WIN triples after approved merge, **not** yet measured on main |
| 3 `OFFICIAL_FINISH_NOT_COMPLETE` | F4 2 Nov #5/#6/#8 | Original `/completeresults` has explicit `isComplete=false`; 9/11, 15/16 and 12/15 result rows vs prestart active fullfields. A provisional place=1 row does not override the official completeness gate |
| 1 `CONFLICTING_OFFICIAL_RESULT_RECEIPTS` | S2 3 Nov #8 | Independent original source receipts disagree; no source-based resolution or retrospective model promotion |

**Diagnosis:** For the six blocked models, eight missing active rosters and three incomplete results, the code is correctly fail-closed on source evidence available here. No responsible numerical uplift is justified. The four pre-frozen scratch mismatches are a genuine isolated implementation defect with a candidate source-grounded repair in PR #138. The distinct official receipt conflict stays open. Later model/result data never change an earlier source gate or T−4 freeze.

**PIT/BET remain OFF.** None of the 67-race original audit rows establishes independent PIT, and no model coefficient, stake, price, V3.3.12 score or hardgate changes are proposed here.
