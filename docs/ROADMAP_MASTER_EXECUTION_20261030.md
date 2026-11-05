# Betting HQ – master-roadmap og gjennomføringsstatus

## MVP-021 FINAL ACCEPTANCE / MVP-022 READINESS | 5 November 2026

**Current real main (verified):** `2238a9b891b16cd74ced7eaa581c630dd572f4b9`, 5 Nov 07:13:25 UTC. PR [#143](https://github.com/Maremoo2/Betting/pull/143), [#145](https://github.com/Maremoo2/Betting/pull/145), [#146](https://github.com/Maremoo2/Betting/pull/146), [#147](https://github.com/Maremoo2/Betting/pull/147), [#148](https://github.com/Maremoo2/Betting/pull/148) all **MERGED by owner**. Exact-main [CI 41985709967](https://github.com/Maremoo2/Betting/actions/runs/41985709967) `CI_PASS`, **1,639 passed, 106 skipped**. No new DEV main merge, no prod betting, `bet_authority=false`.

**Post-merge operational CORE-003 P0-A `PARTIAL`:** [41986285369](https://github.com/Maremoo2/Betting/actions/runs/41986285369) and [41987283702](https://github.com/Maremoo2/Betting/actions/runs/41987283702) were workflow SUCCESS but their actual source/Collector/PIT/scorecard/readiness steps **SKIPPED by run execution gate**; zero original artifacts. NOT `OPERATIONALLY_VERIFIED` for PR #146–148. Last full original, genuinely executed CORE-003 is [41911371831](https://github.com/Maremoo2/Betting/actions/runs/41911371831), 4 Nov 21:02 UTC, prior main `3955320482306b1d2fb475c6826502d15b3c03de`: DEV009 artifact **13364215238** index SHA256 `6dd2ab97bc4e2893e22836777290e9f3d985e0a88c99d5b7df57a68fa6cfa019`, **89 physical /39 full fields /34 result-scored model pairs /33 WIN triples /0 PIT**. DEV011 manifest artifact **13363715590**, SHA `e9395a7c4f95062b3752cc1d444f99ab3d8007c4c2250794e2c11ca9e5e94217`: 4,509 GitHub objects,46 complete pages,316 recovered selected originals, five legacy unindexed, six genuine prior source-unavailable indexes and 1 conflicting `S2_NR_2026-11-03:8` official result source. This is **`INCOMPLETE_ORIGINAL_COVERAGE`**, not full source archive acceptance; `download_failures` and integrity must be independently checked on first actually executed post-merge run. MVP019 readiness original artifact **13362413534** SHA `cccbcb4909ccf8d8b2cb1bafa91fba70f74909bd4b276ba62662b728ded52ed9` anchored four source SHAs but current cohort=0 and strict admission=0, no new model/PIT from that run.

**P0-B V1 exact state `OPERATIONALLY_VERIFIED`, overall `FAIL`:** Genuine [V1 audit 41985710357](https://github.com/Maremoo2/Betting/actions/runs/41985710357) artifact **13395494318** receipt SHA `e4377b78c6d3d33ff0ffe68a97cada5e8cdc79dd47d5e73c8b44011be027d4c8`. Restore original watcher run **41934671198**, `hbi-state` artifact **13372739243**; independently downloaded **206,013,908-byte ZIP** exact SHA `4e7f5e5a6cd488303ff30dd6af5375147e97ec1f91f7fbfdb9852e046afd5385` and independently extracted **707,309,568-byte SQLite** SHA `6eb19189fa5c460869fa2295f2e82768157b765d11343b483312b3d4ad2d231a`. Restore 2026-11-05T07:14:35.606226Z, audit run 41985710357, code SHA exact main. Audit JSON SHA `ef34e9077c6058ac2057eb02da6817f9fb7d65484e9423ba933b8bc9522a6586` shows `TEMPORAL=PASS`, `RUNTIME_REPLAY_PARITY=PASS` **364 checked/557 skipped/0 mismatches**; original five late market-provenance differences remain explicit diagnostic, not false erasure. `SETTLEMENT_INTEGRITY=FAIL` **three overdue**, `PROVIDER_INTEGRITY=WARN` **14 historical** (12 LeTROT 403, 1 Rikstoto 500, 1 Rikstoto network unreachable). V1 full acceptance **NOT ACHIEVED**.

**P0-C three overdue settlements (precise physical IDs):** [Skive #82](https://github.com/Maremoo2/Betting/issues/82) 14 Oct S4 race6 selected #8 25 NOK `BLOCKED_SOURCE`, no official raw complete/raceday from V1 original; [Eskilstuna #144](https://github.com/Maremoo2/Betting/issues/144) 3 Nov S1 race7 selected #3 25 NOK, official complete SHA `5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091`, raceday SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d`, numeric `place=0,kmTime="19,1"` **`BLOCKED_CONTRACT_SEMANTICS`**; [NEW Bjerke race8 #149](https://github.com/Maremoo2/Betting/issues/149) 3 Nov BJ race8 selected #2 25 NOK `BLOCKED_SOURCE` lacking raw official complete/raceday. **Corrected prompt discrepancy:** BJ race4 selected #6 ticket `72518502-350a-457e-adce-20ce32b8d163` was **already SETTLED by existing nightly** 4 Nov 23:33:55Z (finish3, gross0,paper net−25,null close/CLV); no DEV state write. Existing settled source URI not independent byte-complete archived proof. Narrow original-derived and negative settlement regression tests proposed in separate research QA PR; no canonical settlement writes or semantic relaxation.

**P0-D PIT:** `src/hbi/core_t4_receipt.py` after #148 has **`MAX_WAIT_SECONDS=360`** and pre-GET T−4 check, but latest post-merge CORE-003 **skipped** capture, so this 360s behavior is `MERGED / CI_PASS / NOT YET OPERATIONALLY_VERIFIED`. Latest real PIT artifact **13362753002** has 0. Future watch (no PIT promise) source from [provider smoke 41985710135](https://github.com/Maremoo2/Betting/actions/runs/41985710135): Sweden `ATG:2026-11-05_12_1` 14/14 schema, start 11:20Z, no independent `TMP-*` registration crosswalk, no time-qualified official scratch/PIT; next-day NO Biri `ATG:2026-11-06_96_1` 12/12 schema also source-only. No autobet or duplicate automation.

**P0-E provider:** [smoke 41985710135](https://github.com/Maremoo2/Betting/actions/runs/41985710135) `FAIL NO_FULL_FIELD_LIVE_PASS:FR`; artifact **13395883047**, `live-smoke.json` SHA `9b4f88378317ce2ea221882af45f08a58f6e824df065a2c39a27332d5c4c833c`. FR Vincennes `2026-11-05_63_1` active18, 17 history rows, #16 `INVALID_LIFETIME_COUNTS`, #18 `IDENTITY_NOT_UNIQUE_OR_MISMATCH`; other French candidates have `PROVIDER_RACE_IDENTITY_OR_TIME` or `LETROT_FULL_FIELD_CORROBORATION_FAILED`. Separate LeTROT HTML 200 does **not** validate history/fullfield nor clear past HTTP403. **No proven implementation bug, do not lower criteria**.

**30-race milestone and MVP-022:** First **30 distinct chronological same-freeze WIN triples** from original artifact 13364215238 frozen **as retrospective exploration only** in [first30 source lock](MVP022_FIRST30_EXPLORATORY_SOURCE_LOCK_20261105.json), plus separate comprehensive 30-row/60-raw-result rehashed ledger SHA `08de79b2df0ffcec10b2711e6d6661c07c03d2dbca34a389d7ac86189905c5b7`. Exact identical-n=30 log loss **Champion 2.1290872503; CORE004 2.0876948876; normalized WIN 1.9491062640**. Multiclass Brier **0.8614155898; 0.8480727641; 0.8235196459**. Only **3 days /6 racedays**; no robust calibration/inference/EV/betting authority. [MVP-022 future-only prereg protocol](MVP022_PREDICTIVE_EDGE_PREREG_PROTOCOL_20261105.md) proposes owner-signed SHA lock no earlier than first Monday 9 Nov 00:00 Oslo *if signed before*, otherwise a future Monday at least 24h postapproval; first 4 complete weeks validation, next 4 untouched holdout, future replication. `READY_FOR_OWNER_REVIEW` only, no training, no prospective start before signature.

**Manual QA:** `MANUAL-QA-001` 4 Nov, **owner-supplied not independently original-betting-slip audited**: six manual V5/V4X/DDX tickets, **632 NOK stake, 0 NOK payout, −632 NOK**, an unsupported-positive-EV/manual discipline departure, **not** a proven Champion or CORE004 bug. Non-model entertainment/risk illustrations must never be labelled calibrated `BET` or source-proven EV. No changes to historical V3.3.12.

**Permanent source archive:** [EU immutable owner decision](MVP021_EU_IMMUTABLE_ARCHIVE_OWNER_DECISION_20261105.md), no deploy, e.g. EU WORM object storage, versioned SHA/UTC manifests, 365d owner-proposed retention, least privilege, GET budget, independent daily read-back and recovery tests; cost scenarios not vendor quote; `BLOCKED_INFRASTRUCTURE`.

**Status by 13 Nov 18:00 Oslo:** Source/V1 exact-state and first30 research cohort **DONE**; settlement V1 `FAIL`, original-independent PIT 0 `BLOCKED_SOURCE`, FR smoke `FAIL` by source; CORE003 post-merge QA `PARTIAL` pending actual executed run; archive `BLOCKED_INFRASTRUCTURE`; MVP-022 `READY_FOR_OWNER_REVIEW` only. **MVP-021 FULL ACCEPTED not established, production betting remains BLOCKED and `bet_authority=false`.** All previous roadmap sections retained verbatim; no owner merge by DEV.


## MVP-021 | Exact-state V1 integrity, PIT and 30-race benchmark | 4 November 2026

**Review state** (`MERGED` vs `CI_PASS`): `main=4fe98264522e8453589a83bda6d9e59c53b22147`; #140 and #142 merged by owner; #141 historical merged to dev only, its capabilities now on main via #142. [PR #143](https://github.com/Maremoo2/Betting/pull/143) remains **OPEN / DRAFT / mergeable / not merged**. Prior exact-HEAD [41896033401](https://github.com/Maremoo2/Betting/actions/runs/41896033401) passed 43/43 workflow steps (1608 pytest passed, 104 skipped), but that was **before** the MVP-021 audit-identity extensions. Report final revised HEAD CI separately; never infer pass from an earlier commit.

**P0-A V1 restore provenance `IMPLEMENTED / CI_PENDING / NOT_MERGED`:** existing PR #143 stores original `hbi-state` artifact ID, source watcher workflow run/branch/SHA, original ZIP SHA256 and streamed restored SQLite SHA256/size. MVP-021 hardens the exact restore receipt with **UTC `restored_at_utc`, V1 audit's own `audit_workflow_run_id` and checked-out `audit_code_sha`** supplied from `GITHUB_RUN_ID` / `GITHUB_SHA`; missing, malformed or inconsistent audit identity fails before any source GET. The V1 audit workflow independently checks the fields, receipt timestamp, exact database bytes/size and uploads this metadata with failing audit results. This feature is **NOT YET DEPLOYED** until owner merge. Historical audits have no truthful audit-owned receipt; do not backfill one. First actual owner-approved post-merge V1 audit and its artifact are required for `OPERATIONALLY_VERIFIED`.

**P0-B five runtime replay FAIL / evidence-limited causal isolation:** SHA-pinned historical watcher candidate [41890574018](https://github.com/Maremoo2/Betting/actions/runs/41890574018), state artifact 13352639685, extracted SQLite SHA256 `aacf2d95117e1f6eee24fa19ec3df20e220fa84d4e712e3e025dd670e770e7db`, matches audit decisions/fetch totals but **not independently proven to be V1 audit's exact restored bytes**. On this candidate all five decisions reproduce stored combined probabilities and conflict score from the *original saved normalized market vector*; later-attached `decision_provenance.market_odds_json` differs from stored original normalized market by up to 0.01986, 0.03734, 0.03411, 0.03354, 0.06780 p points respectively and creates both existing replay mismatches. Provenance timestamps follow original decisions by ~6–12 minutes. This is a **strong, independently reproduced provenance/market-first divergence**, not proof of code-formula defect or authorized rewrite. Until audit-owned exact state receipt and authentic decision-time odds bytes exist, status remains `FAIL / PARTIAL_CAUSAL_DIAGNOSIS`; no false audit PASS or history patch.

**Independent five-race forensic details:** [MVP-021 source-market parity replay](MVP021_FIVE_RUNTIME_PARITY_ORIGINAL_DIAGNOSIS_20261104.md) gives all original decision/provenance UTC timestamps, exact candidate SQLite SHA, code-attachment SHAs, original log-pool and conflict scores, and precise reasons for retaining FAIL. Audit-owned exact source still requires an actually executed post-merge PR #143 restore receipt.

**P0-C separate settlement blockers:** [Skive #82](https://github.com/Maremoo2/Betting/issues/82), 14 Oct S4 race 6, paper WIN #8 25 NOK vs stored #5 winner, still **BLOCKED_SOURCE** (no authenticated full complete+dividend original). [Eskilstuna #144](https://github.com/Maremoo2/Betting/issues/144), 3 Nov S1 race 7, paper WIN #3 25 NOK vs official #6, has both authentic result originals, raw `completeresults` SHA `5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091` and `raceresults` SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d`, winner dividend status Dividends 5.33. Selected #3 is `place=0, kmTime="19,1", odds=24`; frozen nightly contract only admits placed losers or exact qualified `Dsk`. Authoritative semantic mapping to unplaced runner is not independently attested: **BLOCKED_CONTRACT_SEMANTICS**. No canonical settlement, P/L or CLV changes; both issues open.

**P0-D Jägersro S3 4 Nov race 5:** scheduled 20:30 Oslo, conservative T−4 20:26 = 19:26 UTC. Previous 41895943029 produced a pre-cutoff, too-early PIT snapshot; after-cutoff [ordinary CORE-003 41897182938](https://github.com/Maremoo2/Betting/actions/runs/41897182938) PIT `pit003a-attestations` artifact **13355962432** SHA `74c8e670e16e12e635a63a9790902beebe5bf2cdd0e2ecf1ae4e1e077bc9a925` has `results=[]`, `pit_certified_count=0`; `pit003a-source-receipts` **13355553911** SHA `9f95158440f7c8593097c2b1bf7bd7bad9ef5a322c70baf3bbb5758dd178365b` contains `records=[]` and a plan created 19:28:12 UTC, **after** T−4. Morning start roster/9/9 ATG and time-qualified 19:02 WIN are research evidence, not independent original publishing/horse-identity/scratch attestation. All nine registration IDs `TMP-*`. Official complete-results fetched 19:30:50 UTC SHA `6be26a47eb50f61a64b64c85e9330853fa802e9f074ef4d9e66b7bde4205b7c5` returned `isComplete=true` but nine horses `place=0, kmTime="0,0"`, no unique winner: `OFFICIAL_WINNER_NOT_UNIQUE`; never count a result or PIT. **PIT_NOT_CERTIFIED / BLOCKED_SOURCE**, aftercheck must independently evaluate if new original appears; no retro-certification or duplicate automation.

**P0-E newest original benchmark `OPERATIONALLY_VERIFIED`:** 4 Nov [successful ordinary CORE-003 41897182938](https://github.com/Maremoo2/Betting/actions/runs/41897182938), DEV009 original scorecard artifact **13356727378**, `index.json` SHA256 `9a0fee8f93640dd348e4c4e8310b0383ea790b873e702010e0ddecba4fe55521`: **88 distinct physical races, 38 complete frozen model full fields, 28 officially result-scored Champion–CORE004 pairs, 27 complete same-freeze WIN triples, 1 model-only, 60 not-evaluable, 0 PIT-certified**. The latest readiness artifact **13356322147**, SHA256 `96ab605d160b5086db9cae159c8e100d64d86a7d669ffe2d77e501e3351c1e42` validates all four original source-SHA anchors: scorecard `9a0fee8f...`, current source report `7da154f72fe35f082b4ee30e426cf6379cf3866192b27e90683179b840f87591`, cohort `fd4c43146f1c1731590fdb9426dfbe252b09ec13b6f8d95d599b3a5f5065c079`, DEV011 `a9aaa04da898267c478061a4ba5c93d0146e97c5f850c1f87d83e53efc986aa4`. Seven current source races (five `BLOCKED_IDENTITY`, two `BLOCKED_ATG_FULL_FIELD`), zero strict approved Collector origins, current-only `RIKSTOTO:S2_NR_2026-11-04:10` excluded from cumulative denominator. **27/30** is a research data-volume milestone progress only. Scorecard calibration `INSUFFICIENT_DISTINCT_RACES`, minimum 30. No locked 30 cohort until three more qualifying authentic triples.

**27 identical-race predictive triples (log loss / multiclass Brier, lower better):** Champion **2.087672 / 0.853000**, CORE-004 **2.027578 / 0.833226**, normalized same-freeze WIN **1.932626 / 0.812759**. This dataset contains dependent races and is not proven calibrated; not a BET/EV/CLV result. No model tuning, test-cohort selection after results, replacement of frozen model or independent PIT inference.

**P0-G DEV011 runtime original GET rate limit – independently reproduced source-quality bug:** successful [CORE-003 41898656060](https://github.com/Maremoo2/Betting/actions/runs/41898656060) fully paginated 4,234 artifacts / 43 pages but subsequently received repeated **HTTP 403 GitHub installation API rate-limit** responses to individual `gh run download`. DEV011 manifest artifact **13357447410** SHA-256 `2f8f0341808be0e5f19346f0a24b33126714152b6ae5bf3cf671c3bf83fbe63b` has just **112/308** selected originals recovered, **191** missing/unverifiable + five legacy-unindexed and **0** pinned result races checked. This source degradation improperly allowed partial DEV009 scorecard **13356948878** (SHA `763b0adcb566064d8422f64186ff6561e5a325a1a821939db15e211c850f569f`) with apparent regression 52/22/18/17. **Not a new valid benchmark; previous 88/38/28/27 source-backed result from 41897182938 remains last trusted.** Newly documented and isolated [draft PR #145](https://github.com/Maremoo2/Betting/pull/145) captures each failed source GET in immutable metadata-only TSV and makes existing MVP016 guard publish `source-unavailable.json` / `BLOCKED_SOURCE` with no scorecard `index.json` whenever any required original download fails. It never manufactures a historical result, weakens provenance or changes Champion/CORE004/PIT/BET. Status **IMPLEMENTED / CI_PENDING / NOT_MERGED**, owner approval required; long-term rate-budgeted immutable archive remains separate infrastructure task. Full original receipts: [MVP-021 source-outage report](https://github.com/Maremoo2/Betting/blob/fix/mvp021-dev011-download-failclosed/docs/MVP021_DEV011_RATE_LIMIT_SOURCE_OUTAGE_20261104.md) in PR #145.

**P0-F new source readiness candidates, as-of 19:28:20 UTC (20:28 Oslo):** S2 4 Nov race7 0/12 ATG, T−4 19:37 UTC, `BLOCKED_ATG_FULL_FIELD`; S3 race6 0/12 ATG, T−4 19:48, same; S2 race8 11/11 ATG, T−4 19:59, `BLOCKED_IDENTITY`; S3 race7 11/11 ATG, T−4 20:11, `BLOCKED_IDENTITY`; S2 race9 12/12 ATG, T−4 20:22, `BLOCKED_IDENTITY`; S3 race8 10/10 ATG, T−4 20:36, `BLOCKED_IDENTITY`; S2 race10 12/12 ATG, T−4 20:47, `BLOCKED_IDENTITY`. All seven lack complete, original time-qualified WIN in this snapshot; independent registered ID crosswalk, official scratch receipt and verified Collector source blocked. Never choose expired-race T−4 retrospectively; future candidate should be selected only from a fresh future eligible source cohort.

**P1 external provider/archive:** prior V1 audit historical provider 12 LeTROT 403, 1 Rikstoto 500, 1 unreachable. Distinguish external access-control/HTTP/network from actual parser defects (none proven), do not clear WARN using a green smoke on a later time. Permanent external retention service not approved; propose owner-approved encrypted versioned object storage, WORM/object lock, IAM separation, immutable source URI/UTC/SHA manifests, periodic read-back restore drills, short-lived credentials, no infrastructure write or deploy.

**MVP acceptance by 13 Nov 18:00 Oslo:** demand actual post-merge V1 run whose own restore receipt has verified artifact ID / source run / ZIP SHA / SQLite SHA / restored UTC / audit run / checked-out Git SHA. Demonstrate no five discrepancies or an honest red exact-state diagnosis; recover official Skive contract bytes and resolve Eskilstuna semantic authority before settlement; PIT requires independent original T−4 source/identity/roster proof, not retroactive reconstruction. Benchmark >=30 is a *research coverage milestone*, never standalone betting eligibility. Never merge without owner consent or change frozen Champion/CORE004/V3.3.12/value gates. `bet_authority=false`.


## MVP-020 | Operational readiness, PIT evidence and V1 exact-state recovery – 4 Nov 2026

**Verified `main`:** `4fe98264522e8453589a83bda6d9e59c53b22147`, owner merge #142 at 18:57:28 UTC; #140 previously merged, #141 merged only to dev then fully delivered by #142. GitHub Actions `CI` run **41892221936 PASS**, V1 audit **41892221873 FAIL**.

**P0-A OPERATIONALLY_VERIFIED:** first successful ordinary [CORE-003 41892222531](https://github.com/Maremoo2/Betting/actions/runs/41892222531) on exact main SHA generated MVP-019 source readiness artifact **13353059281**, original `index.json` SHA256 `3424873d6b2a5b26dd25f59885a0a4cc63cf1e4d7621e041f14cb945919c4188`. Independent four-source original checks: cumulative scorecard **13353313617** SHA `be179e26eddab8ac41ec21b79f0acd9acfba106e8fe0177c0d06a628b68cb9a1`, CORE source **13354847436** SHA `809af8ac8919d49f6b564d502effb010f47c62d7ca67019eed63224bc5e22453`, model cohort **13354606909** SHA `0471d143c369276cd7230610343039fd85ab417cdf1e86db0e83e3162a3afa8a`, DEV011 manifest **13352954946** SHA `24b917f1d436b89991b949ae605dc77795598d5931150ffba522cf6712788f54`. **86 physical / 36 full frozen model fields / 26 scored original model pairs / 25 same-freeze WIN triples / 0 PIT**; benchmark remains `INCOMPLETE_ORIGINAL_COVERAGE`. Seven current source races: five `BLOCKED_IDENTITY`, two `BLOCKED_ATG_FULL_FIELD`, zero strict Collector admission. `RIKSTOTO:S2_NR_2026-11-04:9` is source-only, not a cumulative model or result, just as older `RIKSTOTO:S3_NR_2026-11-04:4` reproduced in MVP-019B original replay.

**Additional completed main observation at 19:02:49 UTC:** ordinary [CORE-003 41892671529](https://github.com/Maremoo2/Betting/actions/runs/41892671529), scorecard artifact **13353618670** original SHA `cfbb4aeb10cdfd502d39c13d1a72838cf7633015f174937a43f3e15b51e69d9b` gives **87 physical / 37 complete / 26 paired / 25 WIN triples / 0 PIT**. Readiness artifact **13353443847**, original SHA `89897b4a878d5304942b7e1bb666d0d5ab5d0657a092f44a63fef6a014432956` verifies all seven current source races now occur in cumulative physical archive; physical row S2 race 9 is newly archived **without** adding score or WIN. Jägersro race 5 gained complete original WIN at **19:02:45 UTC** while still before conservative 19:26 UTC T−4; independent registration and official scratch provenance remain blocked, no PIT. Earlier main 41892222531 correctly had WIN incomplete at 18:58 UTC, not a contradiction. **Current milestone: 25/30** valid triples.

**P0-B PIT BLOCKED_SOURCE:** Jägersro `RIKSTOTO:S3_NR_2026-11-04:5` start 20:30 Oslo/T−4 20:26 if clock unchanged; actual original source sampled 18:58 UTC, 9/9 ATG, all registration IDs `TMP-*`, morning starts SHA `fe1cde9c8642d8f526eb95c69c524c7b24243ba6669540f9126197e5ff4ea386`, PDF SHA `ddbe3bf9fe96dd04492509c184de9ae6491e9660f4f2772d2b8f07645eb74ba2`, WIN missing, independent cross-ID and final T−4 scratch source unverified, research model not independent PIT. No later evidence projected backwards, no second automation.

**Later completed checkpoint at 19:11:46 UTC:** [CORE-003 41894514024](https://github.com/Maremoo2/Betting/actions/runs/41894514024), scorecard original artifact **13356205369** SHA `0168abb3ecc7143706321383099dc5ef76c1a9ad5820c6f7f4fca7029919b5bf`; readiness original artifact **13356550052** SHA `eaf40b72317ff40b78f21a2879b7e8284db7c5a96dd62a4d8a493e00036f59d4`. **87 physical / 37 complete / 27 result-scored pairs / 26 WIN triples / 0 PIT**. New source-only `S3_NR_2026-11-04:8` outside cumulative archive; independent original no PIT or fabricated outcome. Frozen same-race 26-triple means: log loss Champion **2.134770**, CORE004 **2.094102**, normalized WIN **1.973956**; Brier **0.866808 / 0.855951 / 0.827464** respectively, no economic EV evidence, calibration still insufficient. **26/30**, gap 4. Latest research shortlist as-of this run excludes expired S2 race6 and comprises S3 race5, S2 race8, S3 race7, S2 race9, S3 race8, with 9/9, 11/11, 11/11, 12/12, 10/10 ATG active histories respectively; every race lacks independent full-field registered IDs and official time-qualified scratch proof, WIN only complete for S3 race5.

**P0-C settlement FAIL:** Skive #82 remains source-blocked; Eskilstuna numeric `kmTime` frozen-contract decision in [#144](https://github.com/Maremoo2/Betting/issues/144). Candidate historical watcher SQLite from [41890574018](https://github.com/Maremoo2/Betting/actions/runs/41890574018), artifact **13352639685**, extracted SHA `aacf2d95117e1f6eee24fa19ec3df20e220fa84d4e712e3e025dd670e770e7db`. Skive #82 ticket `a55a504a-bc34-487d-aced-75326dcb2b59` remains `BLOCKED_SOURCE`: 25 NOK paper #8, no official result+dividend originals in archived SQLite. Eskilstuna 3 Nov ticket `f2b7e174-c650-4709-8cbb-924c30413ab9` original 25 NOK paper #3: official complete+raceday source bytes **do exist** in scorecard artifact 13353313617, HTTP 200, complete SHA `5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091`, raceday SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d`: official winner #6, Dividends 5.33, chosen #3 `place=0 kmTime="19,1"`. Frozen `nightly.py` contract accepts `place>0` or uniquely confirmed `Dsk` for losing selection; numerical time at place 0 requires separate semantic approval. No historical settlement, P/L, refund, closing price or CLV write.

**P0-D replay FAIL / PARTIAL_SOURCE:** new [V1 audit 41892221873](https://github.com/Maremoo2/Betting/actions/runs/41892221873), artifact **13353612873**, original audit JSON SHA `c3c98894efac5c7f6d630d488988aa7d4048faa804bd68437f2df41b47d648f8`, still five replay failures, two overdue paper tickets, provider WARN 14. Strong candidate state artifact 13352639685 was created 18:48:08 UTC and matches audit 909 shadow decision / 15265 provider GET counts. **Historical audit DID NOT RECORD selected artifact ID/SHA**; source identity cannot be certified retroactively from coincidental row counts. Independent read-only replay of five decisions against candidate's original stored market probabilities reproduces combined (p) and conflict scores exactly; later-attached market-odds provenance differs, max combined `p` deltas 0.01141, 0.05808, 0.03187, 0.04096, 0.07896. This is market/provenance divergence, **not demonstrated model formula corruption**. New PR `dev/mvp020-v1-exact-restore-receipt` adds optional exact restored artifact ID, ZIP SHA and SQLite SHA receipt to V1 audit only, fail-closed, without altering historical decisions or audit PASS/FAIL. Status `IMPLEMENTED / CI_PENDING` until exact PR HEAD tests.

**P0-E prospective quality:** stage counts on first main original snapshot: 7 DISCOVERED, 7 original-startlist SOURCE_CAPTURED, **0 strict VALIDATED / MODEL_ELIGIBLE / PIT-FROZEN / newly RESULT_VERIFIED / newly WIN_EVALUABLE**. Five research-only model invocations are **not** valid PIT freezes. As-of-source candidates (not valid after cutoff): S2 race6 (ATG9/9 WIN complete), S3 race5 (ATG9/9), S2 race8 (ATG11/11), S3 race7 (ATG11/11), S2 race9 (ATG12/12). Independent registered horse identity/official scratch-original gates block all; WIN incomplete except S2 race6. Two further races S2 race7 and S3 race6 are ATG 0/12. Never pick expired races as new prospective freeze candidates.

**P1 original archive / provider:** external immutable object-store + SHA/UTC manifest + object lock/WORM, key rotation, role separation, periodic restoration drill proposed, NOT DEPLOYED or authorized. Provider 12 LeTROT HTTP 403, 1 Rikstoto HTTP 500, 1 unreachable; do not clear historical WARN using separate green smoke. Benchmark **25/30** identical-race same-freeze WIN triples; gap five without model or odds changes.

**Evidence:** [full MVP-020 audit and original receipts](MVP020_OPERATIONAL_ORIGINAL_P0_AUDIT_20261104.md). Date-critical work remains deadline 13 Nov 2026 18:00 Oslo. **No main merge in DEV, no new automation, `bet_authority=false`.**



## MVP-019B – owner integration, original benchmark reconciliation and disjoint source fix | 4 November 2026

**Grounded repository state at review:** owner merged [PR #140](https://github.com/Maremoo2/Betting/pull/140) to `main` at 17:40:52 UTC, merge SHA `640908bfc7f3aa01c80ddb8daca81d0846835068`. Owner merged [PR #141](https://github.com/Maremoo2/Betting/pull/141) at 17:41:23 UTC **into `dev/mvp018-original-model-freeze-provenance`**, not `main`. #141's branch and tests therefore remain **NOT IN MAIN**; a merged PR cannot simply be retargeted. No DEV main merge. All model and betting policies remain frozen.

**Original scorecard reconciliation, fully source-audited:** [41832416078](https://github.com/Maremoo2/Betting/actions/runs/41832416078), artifact 13324990108, original SHA `a4a667bd596bde42b9e3dbed6d96247731067fe76f82b33ea816194fa68b5ff7`, had 67/24/**16**/**14**. After #138 [41842113458](https://github.com/Maremoo2/Betting/actions/runs/41842113458), artifact 13328604183 SHA `99634bb9654e71fcf1616ae145a9da6af1ce020569ec8a98a1d315c4fd0824ec`, had 68/24/**19**/**18**. Exactly 4 old `OFFICIAL_ACTIVE_FIELD_MISMATCH` races `S2_NR_2026-11-02:{1,2,4}` and `S2_NR_2026-11-03:9` became both scored pairs and WIN triples with unchanged selected model/SHA; previous model-only `S1_NR_2026-11-03:3` exited because #9 Queen Montana was **active at frozen model time**, later officially `Str`, a correct `OFFICIAL_LATE_SCRATCH_NOT_FROZEN` denial. Arithmetic +4−1=+3 pairs; +4 WIN triples. Original WIN observation clocks and official SHA receipts are documented in [full five-race reconciliation](MVP019B_FOUR_SCRATCH_ORIGINAL_RECONCILIATION_20261104.md). The extra physical race did not affect the delta. No original relabels or hindsight replacements.

**Latest verified post-#140 ordinary source, snapshot 4 Nov 17:49 UTC:** [CORE-003 41880220139](https://github.com/Maremoo2/Betting/actions/runs/41880220139) on main `640908bfc7f3aa01c80ddb8daca81d0846835068` is `OPERATIONALLY_VERIFIED`: DEV-009 original artifact **13350305285**, SHA256 `03223d1b4f62e1a75eda0681ca60d49cc66f657d8866904b0c75ca8027cfd4bd`, **80 physical / 32 complete model fields / 21 scored model pairs / 20 same-freeze WIN triples / 0 PIT**. MVP-019 readiness artifact is **absent on this main run** because merged historical #141 is not deployed on main; no operational readiness claim. Previous original 418790 completed success after earlier pending snapshot.

**Newest fully completed ordinary observed benchmark:** [CORE-003 41876750467](https://github.com/Maremoo2/Betting/actions/runs/41876750467), artifact 13347262179 SHA `2416b18f14f0c1acec80c22574656276529facc6243cb9a0b86a8e836c738a74` is **78 physical / 30 complete frozen fields / 20 result pairs / 19 WIN triples / 0 PIT**. Later [CORE-003 41879063497](https://github.com/Maremoo2/Betting/actions/runs/41879063497) original scorecard artifact 13349440390, SHA `6ec0392fd9620b41be90610b5348a019e0a9e43a975562960f8f04d2cbd61a9a`, reports **79 / 31 / 20 / 19 / 0**, ordinary workflow subsequently completed successfully; this 79/31/20/19 is a verified intermediate snapshot, not the latest main result.

**Actual documented implementation failure:** The original 418790 current cohort has **7** physical race IDs, 6 overlap historical cumulative scorecard; `RIKSTOTO:S3_NR_2026-11-04:4` is processed in the current source index but not yet in the cumulative archive. Original cohort SHA `f3af0f08f203044b0cede78ca41b395828144aad794ec21ace3ef4520541dec7` references exact source SHA `ab5a773ef530b061659d2ff2ee78f16806fd97637be6c57f29768d9c51cad560` and cumulative DEV011 SHA `a9b5c7efa0a35191f4693658df58161d553556f3dcc4e1ecc638a2c8b0c4a01e` shares scorecard inventory SHA. MVP-016's `set(current) <= set(scorecard races)` requirement incorrectly blocks this valid **different-horizon** current source; MVP-019B fixes its read-only readiness consumer without inventing a new cumulative scorecard row. Separate denominators: 79 cumulative, 7 current, 1 current-only, 80 union-not-benchmark. Regression replays use the four original SHA-pinned GitHub artifacts and fail closed. New source-readiness artifact remains pending owner-approved integration to `main`, not operatively delivered by historical merged #141.

**Prospective source shortlist, as-of 17:38 UTC:** `S3_NR_2026-11-04:1` and `S2_NR_2026-11-04:3` both have 11/11 complete ATG history and WIN; `S3_NR_2026-11-04:2` has 11/11 ATG, `S3_NR_2026-11-04:3` 8/8 and `S2_NR_2026-11-04:5` 9/9, the last three still lack complete WIN. All five have zero independently attested stable horse IDs/cross-provider registration and no qualified official T−4 scratch receipt, zero collector model approvals and zero PIT. One source-only current race S3 #4 remains out of cumulative benchmark. S2 #4 has additional real ATG/roster/SQLite mismatches. Never approve by name matching, unvalidated TMP registration or archived later results.

**Main V1 audit still fails:** [41879477950](https://github.com/Maremoo2/Betting/actions/runs/41879477950), artifact 13347244894 original audit JSON SHA `54f01128607fc59b27a5fb7723d9ef3f165cfe01308af40af1a7b18672cb3fb6`: temporal PASS, five unchanged combined-probability/conflict-score mismatches, **two** overdue unsettled paper tickets (Skive #82 and Eskilstuna 3 Nov `f2b7e174-c650-4709-8cbb-924c30413ab9`), provider WARN 12 letrot HTTP 403 + 1 Rikstoto 500 + 1 unreachable. Restored main watcher state [41878788182](https://github.com/Maremoo2/Betting/actions/runs/41878788182), artifact 13348416076, independently extracted SQLite SHA `10d77c71c6f07910ed94aa3bfc3a9c642404b1451c227408fc7207f84c624f57`; matches 905 decision-run/15195 provider fetch counts, while audit workflow itself does not publish selected state artifact ID or SHA. Historical five decision provenances were attached after decisions, not proof of reproducible original-time policy. No settlement, history edit or fail-gate downgrade.

**Jägersro:** prospective T−4 planned 20:26 Oslo for `RIKSTOTO:S3_NR_2026-11-04:5` if official start is unchanged, scheduled aftercheck is existing owner work only. Not PIT-certified. External append-only WORM storage remains `BLOCKED_INFRASTRUCTURE`; local #135 tooling not deployed long-term. No new automation. `bet_authority=false` end-to-end.

| Gate / delivery | Verified status |
|---|---|
| #140 merged direct main, full existing CI | **MERGED / CI_PASS** |
| Historical #141 feature merged into side branch, not main | **MERGED_TO_DEVELOPMENT_ONLY / NOT_IN_MAIN** |
| MVP-019B disjoint-source implementation/tests on research branch | **IMPLEMENTED / CI_PENDING** until exact-HEAD original replay |
| 16/14 to 19/18 model/official result reconciliation | **OPERATIONALLY_VERIFIED original SHA** |
| Current same-run source-only race source identity | **ORIGINAL_VERIFIED / RESEARCH_ONLY** |
| Independent PIT, registration, scratch, fixed source gate | **BLOCKED_SOURCE**, zero |
| V1 exact-state integrity & settlement | **FAIL** |
| Permanent external original archive | **BLOCKED_INFRASTRUCTURE** |

**Next action:** owner must separately approve main integration of the source-readiness feature through an unmerged integration PR; merged historical #141 cannot be retargeted. Independently verify exact final PR HEAD CI and first ordinary post-main CORE-003 readiness artifact. Do **not** merge automatically or create any betting execution/automation.




## MVP-018 – Operational original checkpoint | 4 November 2026, 13:15 UTC

**Newest dated append-only checkpoint.** `main` initially `d0bb18d30b27d0ca62f2c74331f52b42ca90a2a1`; main later advanced to `f105f96b769e5544dfd7ab6a5b3ebf7657fccd77` after owner-side merge of MVP-017 health PR #136. #132/#134/#133 remain merged. PR #135 (local archive), #137 (27 original freezes), #138 (pre-frozen scratches), #139 (prospective funnel) are open; no merge by DEV in this sprint.

**Latest validated ordinary main source:** [CORE-003 41832416078](https://github.com/Maremoo2/Betting/actions/runs/41832416078), original DEV-013 scorecard artifact **13324990108**, raw JSON SHA256 `a4a667bd596bde42b9e3dbed6d96247731067fe76f82b33ea816194fa68b5ff7`. **67 unique physical races, 24 complete eligible frozen full-field models, 16 official result-scored Champion/CORE-004 pairs, 14 eligible same-freeze WIN triples, 2 pair-only, 0 archive errors, 0 independently PIT-certified**. Operative 67 / 16 / 14 is **not** the prospective uplift from #138, which remains `CI_PASS / NOT_MERGED`.

Original first reason distribution at 67: **29** no verified frozen model, **8** frozen field missing, **6** invalid Champion full field, **4** official active-field mismatch, **3** official result incomplete, **1** conflicting official result. The original 27 no-freeze root audit is separately time-scoped to 65 physical races and must not be reclassified as 29 historically missing without new source evidence.

**Code and evidence, not policy promotion:**
- #137 original diagnostics: 27 missing model freezes traced across SHA-pinned original fixed cohorts, with 9 historical PDF parser rejects now covered by previously merged DEV-012 and no historical backfill.
- #138 original-results fix: four already pre-T-4 frozen scratches are present in official results as `place=0, kmTime=Str`. Expected research-only scoring uplift +4 pairs / +4 WIN triples **after explicit owner merge** and ordinary original re-evaluation. No change to active model p(win), outcome-selection rules, PIT or V3.3.12. Other six blocked, eight missing and three incomplete are documented with exact source classes in the #137 audit.
- #139 new four-original-provenance funnel: latest three fixed F1 races had three Collector source SHA receipts, **zero independently approved model inputs and zero current model processing**. The cumulative 67→24→16→14 funnel is a separate denominator; intermediate source-capture rates for all historical 67 remain **UNKNOWN**. [CI 41836112539](https://github.com/Maremoo2/Betting/actions/runs/41836112539) **PASS**, 1,561 tests passed, 90 skipped and authentic 4-original replay; metadata only. Not merged.
- #135 local original archive code remains `CODE_COMPLETE/CI_PASS`, permanent remote retention `BLOCKED_INFRASTRUCTURE`. #136 research health now on main; raw GitHub metadata and cumulative original SHA still gate validity.

**P0 remaining:** 30 triple research target currently only **14/30**, V1 audit **FAIL** (5 runtime replay, 1 Skive #82 unsettled, 14 provider WARN), Jägersro #5 4 Nov independent PIT **0**; preserve scheduled 20:26 T−4 / 22:15 audit without early certification. No new automations, real-money operation, source gate relaxations, model refit, retrospective frozen admission, multi-leg economic EV or changed `bet_authority=false`.


## MVP-018 – Model Freeze Coverage Recovery | 4. november 2026 | P0 (append-only)

**Påbegynt mot:** `main=d0bb18d30b27d0ca62f2c74331f52b42ca90a2a1`. Ingen historiske snapshots nedenfor er omskrevet. Frist **13.11.2026 kl. 18:00 Europe/Oslo**. [Mandat](MVP018_27_MISSING_FREEZE_ORIGINAL_AUDIT_20261104.md) og original SHA-verifisert GitHub Actions-kjøring [41826525357](https://github.com/Maremoo2/Betting/actions/runs/41826525357).

### Operativ akseptanse etter merge av MVP-016

- **#132, #134 og #133 er MERGED.** Første ordinære CORE-003 på denne eksakte main er [41826525357](https://github.com/Maremoo2/Betting/actions/runs/41826525357). Kumulativ originalt fysisk resultat: **66** distinkte løp, **24** komplette modellfullfelt, **16** resultatverifiserte Champion–CORE-004-par, **14** komplette samme-frys normaliserte WIN-triples, **2** modellpar uten WIN, **0** uavhengige PIT, **0** `archive_errors`. MVP-016 skrev ekte `mvp016-research-status`-artefakt `13319009717` og signerte original/manifest-koblinger. Påfølgende ordinær [41829843268](https://github.com/Maremoo2/Betting/actions/runs/41829843268) er fortsatt **66/16/14/0** uten archive errors. **Ingen ny datadrevet scoret modellobservasjon** etter 65/16/14-baseline. Ny faktisk GitHub-inventarfeil etter merge er ikke observert; full paginerings-fail-closed er separat originalreplay-testet.
- Historisk originalbasert **65/16/14 før** vs **66/16/14 etter**; `NO_VERIFIED_FROZEN_MODEL` **27 → 28** fordi én ny fysisk kandidat kom til uten kvalifisert prospektiv modell. Øvrige førsteårsaker **FROZEN_FIELD_MISSING=8**, **CHAMPION_FULL_FIELD_INVALID=6**, **OFFICIAL_ACTIVE_FIELD_MISMATCH=4**, **OFFICIAL_FINISH_NOT_COMPLETE=3**, **CONFLICTING_OFFICIAL_RESULT_RECEIPTS=1**; dette er en **kilde- og scorecardklassifisering**, ikke direkte programvarefeil.

### Faktisk rotårsak og ny kode

- <Link> [MVP-018 PR #137](https://github.com/Maremoo2/Betting/pull/137) `CODE_COMPLETE / CI_PASS (original trace)` leverer strengt SHA-pinnet `cohort-index.json`-sporbarhet for 27 tidligere manglende modellfrys. Alle 27 var valgt i minst én autentisk kohort før cutoff og avslått før frys. Historisk siste førstekategori: 9 PDF-feltavvisninger, 7 ATG-fullfelt/fundamentaler, 6 roster-/aktivsett-konflikter, 3 uavhengig identitet, 1 PDF-klokkekonflikt, 1 T−4 som allerede var passert. **10/27** hadde komplett observert WIN, **12/27** komplett ATG-historikk ved den utvalgte kilden. 9/9 historiske PDF-feltavvisninger passer nå original PDF/starts under allerede merget DEV-012/#131 parser. **0 historiske modellfrys rekonstruert.** Originaler som ikke finnes i den undersøkte samlingen klassifiseres fortsatt UNKNOWN; ikke `SCHEDULE_NOT_SELECTED`.
- <Link> [MVP-018 PR #138](https://github.com/Maremoo2/Betting/pull/138) `P0 SOURCE-REPRODUCED / CI pending exact HEAD`: fant en separat konkret evaluatorfeil som tidligere ikke var behandlet. **Fire** offisielle `OFFICIAL_ACTIVE_FIELD_MISMATCH` inneholder akkurat de hestene som **allerede var strøket i frosset originalmodell**. Offisiell `completeresults` inkluderer dem som `place=0,kmTime="Str"`, mens gammel kode sammenligner hele resultatlisten bare mot aktive modellhester. Snever rettelse aksepterer kun original-frosset startnummer + navn med eksplisitt `Str` i ekte offisiell resultatsource; ellers fail-closed for sen strykning, annen strykestatus, feil hest, duplikat, manglende aktiv, feil dividende. Original model/run + originalresultat SHA-verifiseres i CI. **Potensial etter godkjent merge og ordinær drift:** 16→20 verifiserte modellpar og 14→18 WIN-triples. Potensialet er ikke en operativ måling, og selve Champions og CORE-004 p(win) endres ikke.

### Andre originalbaserte kildeblokker

| Første scorecard-årsak, 65-race utvalg | Antall | Verifisert kildebevis/tilstand | Neste handling |
| --- | ---: | --- | --- |
| `FROZEN_FIELD_MISSING` | 8 | 7 Øvrevoll-løp + 1 Solvalla har faktisk tidligere `shadow.json`, men **0 aktive hester** og `NO_CANONICAL_ROSTER`; ikke gjenfinnbare gyldige frys | Prioriter ny tidsriktig provider /starts og autoritativ scratch, ingen modell-bakfylling |
| `CHAMPION_FULL_FIELD_INVALID` | 6 | Tre F2, to F4 og én OR har originalt `MODEL_BLOCKED`, null p(win) på aktivt felt, ATG-årsaker (`NO_PROVIDER_RACE`, identitet eller `PROVIDER_RACE_IDENTITY_OR_TIME`) | Dokumentér verifisert providerkapasitet/tilgang, ikke senk source gate |
| `OFFICIAL_ACTIVE_FIELD_MISMATCH` | 4 | Alle fire ekte `MODEL_READY`, komplett Champion+CORE004 og frosset WIN, resultatkvitteringer fra 2–3.11. Før-frosset scratch stemmer eksakt med offisielt `Str` (se #138) | Original replay og framtidig scorecard etter autorisert merge |
| `OFFICIAL_FINISH_NOT_COMPLETE` | 3 | Tre F4-løp har `MODEL_READY`, men original offisiell respons `isComplete=false`; resultat ikke kanonisert. | Krev ny autentisk offisiell *etterløps*-kvittering; ikke fabrikér utfall |
| `CONFLICTING_OFFICIAL_RESULT_RECEIPTS` | 1 | `RIKSTOTO:S2_NR_2026-11-03:8` gamle originale resultatkvitteringer motstrider; ingen valg etter modellen. | Fortsatt BLOCKED_SOURCE |

**Funnel:** `DISCOVERED → SOURCE_CAPTURED → SOURCE_VALIDATED → MODEL_ELIGIBLE → FROZEN → INDEXED → RESULT_VERIFIED → WIN_TRIPLE_EVALUABLE` bygges ut med strenge originale source-state SHA og observasjonstid. De **27** historiske tilfellene er *observed cohort member* men kildeblokkert før modellfrys. Den operative kohorten har **24 komplette fullfelt og 16 offisielt scorede**, ikke 24 godkjente evalueringer. Planlagt CORE-003 provider-budget `max-tasks=4`, 90 min horizon; foreliggende kjøringer beviser ikke at økt frekvens/budsjett ville avhjulpet disse kildekonfliktene; ingen økning eller duplikatautomasjon.

### Integritet, eierakseptanse og M1–M6

| Milepæl | Oppdatert, kildebegrunnet status |
| --- | --- |
| **M1 benchmark** | Ordinær **66/16/14/0**, bare 14/30 første treveis-milepæl. Potensial #138 +4 er **ikke** operativt verifisert. Log loss, Brier og markedsuenighet ≠ kalibrert økonomisk EV eller dokumentert ROI |
| **M2 PIT** | Jägersro `RIKSTOTO:S3_NR_2026-11-04:5` T−4 **20:26 Oslo** kun dersom start kl 20:30 uendret; eksisterende etterkontroll 22:15. Morgenoriginal med 9 `TMP`-identiteter; **0** sertifiserte. Prematur PIT forbudt |
| **M3 originalarkiv** | DEV011 fortsatt `coverage_complete=false`: fem legacy modeller tilgjengelige men uindekserte, én motstridende resultatkvittering. #135 privat **lokalt** append-only arkiv ikke operativ WORM; remote retention **BLOCKED_INFRASTRUCTURE** |
| **M4 V1 integritet** | V1 system audit **FAIL**, fem originale runtime replay-avvik, ett uoppgjort Skive issue #82, 14 provider WARN. Ingen audit-waiver eller oppgjør oppdiktet |
| **M5 V4/V75/V85** | Original fysisk multi-leg identitet og sannsynlighetskjerne finnes; original kombinasjonspris/utbetalings- og jackpotkontrakt fortsatt utilstrekkelig. Ingen pool-EV |
| **M6 13.11 MVP** | Utviklingsmessig betydelig framgang i kildekontroll og målbare evalueringsfeil, men **ingen PIT** og V1 systemaudit FAIL. Bettingautoritet fortsatt OFF |

**Eierprosedyre:** PR #137 og #138 står åpne i utelukkende read-only/P0 forsknings- og evaluatorfiler; **ingen merge uten eksplisitt eiersamtykke**. #135 og #136 er separate draft-PR-er med merge-konflikt løst på eksisterende grener; full CI på nye HEAD kreves. Enhver merge av #137/#138 i vilkårlig rekkefølge kan kreve en ny CI-workflow konfliktkontroll; modell og terskler er urørt. No replay-, provider-, V3.3.12-, Champion-/CORE004-vekter eller PIT-regler er endret.



## MVP-019 | Operational source quality & original admission, 4 November 2026

**Current verified integration branch state:** [PR #140](https://github.com/Maremoo2/Betting/pull/140) is `OPEN/DRAFT` directly against `main`, GitHub mergeable and all four required CI workflows passed on HEAD `98433439e25d96a7a3b49b7fcdc526b262cee23a`. Historical stacked PR #137 was merged into #135's feature branch, and #139 was merged into #137's feature branch; their `MERGED` UI states **did not** place those changes on `main`. Do not repeat or falsely count main delivery. Main was `ee2d5617024b238558072bb24ec92a6b4291c710` when independently inspected. **No DEV merge performed.**

**New diagnostic implementation:** [PR #141](https://github.com/Maremoo2/Betting/pull/141) is `OPEN/DRAFT`, based on #140's feature branch; adds original-joined Source Readiness Matrix, negative regressions and a four-original SHA-checked CI replay. This is research-only. `IMPLEMENTED`; `CI_PASS` and `MERGED` are distinct states and must be checked on its exact final HEAD. The four-source join lacks independently attested per-runner stable identity, official scratch originals and separate official clock receipts, so no source readiness output independently grants `READY_FOR_FREEZE`, PIT or BET.

**Observed ordinary CORE-003 post-#138 data:** [41842113458](https://github.com/Maremoo2/Betting/actions/runs/41842113458) on main `e4cd4b96294030df75af13459f73283b509fe2ae` produced 68 physical races, 24 complete frozen model fields, 19 original-result-scored pairs, 18 same-freeze WIN triples, 0 PIT and incomplete original coverage. Against previous 68/24/16/14, this is **+3 scored pairs and +4 WIN triples**, not the hypothesized 20/18. Four individual scratched-runner race outcomes still require per-original audit; prior CI replay alone is not operational attribution. Later ordinary [41843330305](https://github.com/Maremoo2/Betting/actions/runs/41843330305), on main `ee2d5617024b238558072bb24ec92a6b4291c710`, produced **69 / 24 / 19 / 18 / 0 PIT**, with 50 non-evaluable races. New race discovery **did not** increase qualifying pair count.

| Original-dependent metric | Prior historical baseline | Latest ordinary CORE-003 41843330305 | Status |
| --- | ---: | ---: | --- |
| Distinct physical races | 68 | **69** | OPERATIONALLY_VERIFIED |
| Complete originally frozen model full fields | 24 | **24** | OPERATIONALLY_VERIFIED |
| Scored Champion/CORE-004 original-result pairs | 16 | **19** | OPERATIONALLY_VERIFIED |
| Same-freeze normalized WIN triples | 14 | **18** | OPERATIONALLY_VERIFIED |
| PIT-certified physical races | 0 | **0** | BLOCKED_SOURCE |
| Not evaluable (not equivalent to source-gate root cause) | 52 | **50** | OPERATIONALLY_VERIFIED |
| V1 runtime replay mismatches | 5 | **5** in main audit 41842667032 | FAIL |
| Overdue unsettled paper shadow tickets | 1 | **1**, [#82](https://github.com/Maremoo2/Betting/issues/82) | FAIL |

**Root causes not waived:** historic original source trace for 27 blocked physical races: 9 PDF, 7 ATG full-field, 6 active-roster, 3 independent-identity, 1 start-clock, 1 conservative T−4. Nine PDF original regression checks previously matched post-DEV-012 code but did **not** create retrospective freezes. ATG registration crosswalk, scratch provenance, timing and potential implementation defects require new original evidence. No source-independent fix claimed; `BLOCKED_SOURCE` remains valid.

**V1 evidence:** [main audit 41842667032](https://github.com/Maremoo2/Betting/actions/runs/41842667032) restored a state and still reports temporal PASS, runtime replay FAIL (five combined-probability and conflict-score mismatches), settlement FAIL (Skive ticket #82), provider WARN. Do not compare a different historical SQLite state to claim code error, and do not mark the ticket settled without authenticated official complete result and dividend semantics.

**PIT Jägersro 4 November:** `RIKSTOTO:S3_NR_2026-11-04:5`; original independent registration, official scratches, T−4 freeze and WIN receipts must all be source-verified. Existing scheduled 22:15 aftercheck is owner-controlled; no duplicate scheduling, no retrospective PIT. `bet_authority=false`.

**Next critical path:** (1) owner reviews #140, CI and merge history; (2) validate #141 authentic replay and maintain the read-only matrix; (3) isolate repeated prospective identity/ATG/roster failures using **new original pre-cutoff bytes**, implement only reproducible source-parser/mapping fixes; (4) pinned-state V1 replay and Skive original result, PIT source attestation; (5) increase outcome-paired same-race original benchmark toward 30 without tuning Champion/CORE-004 or changing pricing, gates or stakes. Deadline 13 November 2026 18:00 Oslo. No automatic merge or external writes.


## MVP-017 – Operational hardening and evidence expansion | 4 November 2026


**Nyere originalbasert dekningsdelta:** [CORE-003 run 41822832612](https://github.com/Maremoo2/Betting/actions/runs/41822832612), publisert etter 64-løpssnapshotet nedenfor, viser **65 unike fysiske løp / 16 resultatverifiserte modellpar / 14 gyldige treveis WIN-par / 2 modellpar uten WIN / 0 PIT** og **0 archive_errors**. Den eneste nye fysiske ID-en er `RIKSTOTO:F1_NR_2026-11-04:2`; den har `NO_VERIFIED_FROZEN_MODEL`, ingen kvalifisert WIN og ingen ny modellscore. Av de **49** ikke-evaluerbare fysiske løpene har **27** `NO_VERIFIED_FROZEN_MODEL` som første blokkering, **8** `FROZEN_FIELD_MISSING`, **6** `CHAMPION_FULL_FIELD_INVALID`, **4** `OFFICIAL_ACTIVE_FIELD_MISMATCH`, **3** `OFFICIAL_FINISH_NOT_COMPLETE` og **1** `CONFLICTING_OFFICIAL_RESULT_RECEIPTS`. Dette er avvisningsklassene i originalscorecardet, ikke automatiske diagnoser av programfeil. Hvert løp teller én gang. Tidligere 64-løpsmåling under beholdes uendret som historisk kohort.


**Newest append-only status, not a rewrite of the prior MVP-014/MVP-016 snapshots below.** Original source: [CORE-003 41820503559](https://github.com/Maremoo2/Betting/actions/runs/41820503559), exact [main V1 systemaudit 41820373324](https://github.com/Maremoo2/Betting/actions/runs/41820373324), and the PR original CI replays. Start-main `2937150ee0ce5bb7a0f6bb2ebe9ede7b894d01d3`, owner review required before any merge. Deadline **13.11.2026 18:00 Europe/Oslo**.

### Integration – three distinct source conditions and shared CI

- **[PR #132](https://github.com/Maremoo2/Betting/pull/132)** `MERGED / OPERATIONALLY_VERIFIED`: truly empty authenticated original cohort is now **zero new races and zero archive errors**, not corrupt input. Original main run 41820503559 has **0** `archive_errors` versus **12** on the previous working scorecard; still 64 physical races / 16 original-result model pairs / 14 same-freeze WIN triples / 0 PIT.
- **[PR #134](https://github.com/Maremoo2/Betting/pull/134)** `CODE_COMPLETE / source-replay CI previously PASS / OPEN`: bounded **three full GitHub artifact-inventory retries from page one**; persistent source failure returns `BLOCKED_SOURCE`, null benchmark counts, and no valid cumulative `index.json`. Genuine scheduled [41817026855](https://github.com/Maremoo2/Betting/actions/runs/41817026855) was green but **incorrectly** emitted 0/0/0 after `ARTIFACT_PAGINATION_CONCURRENT_CHANGE`. The owner-visible last-known-valid scorecard must not be invalidated. Updated development branch includes merged #132 replay, no production merge by DEV.
- **[PR #133](https://github.com/Maremoo2/Betting/pull/133)** `CODE_COMPLETE / original join replay previously PASS / OPEN`: operational source report/physical-cohort/DEV011-manifest/DEV013-scorecard joined by original SHA, with per-race coverage, alternative original model freezes, per-track/date distributions, and paired log loss/Brier (n=14; no inferential confidence intervals). **Integration commit stacks #133 on #134** and brings all three regression suites and workflow steps together on an unmerged development branch. Combined CI must pass on its **final** HEAD before owner approval.
- **[PR #135](https://github.com/Maremoo2/Betting/pull/135)** `CODE_COMPLETE / CI_PASS / NOT_DEPLOYED`: **1,547 passed, 87 skipped**, authentic original archive scratch replay, no exposed raw payload; implements local content-addressed immutable SHA receipts with explicit approval requirement and tamper checks. Long-lived **external** object storage, WORM retention/ACL/deployment is `BLOCKED_INFRASTRUCTURE` and not claimed complete.
- **[PR #136](https://github.com/Maremoo2/Betting/pull/136)** `CODE_COMPLETE / OPEN`: separate offline status contract `CURRENT_VALID`, `LAST_KNOWN_VALID`, `SOURCE_UNAVAILABLE`, `INCONSISTENT`, `NOT_EVALUATED`, with authentic 63/16/14 older run, false-zero outage and latest 64/16/14. Last verified metric stays pinned to prior run ID/SHA/time; no old value passed off as current. Final CI on exact HEAD must be independently checked.

### P0 gates, evidence and milestone M1–M6

| Milestone | Source-grounded current measurement | Status |
| --- | --- | --- |
| **M1 – Operational benchmark** | [41820503559](https://github.com/Maremoo2/Betting/actions/runs/41820503559): **64 unique physical races**, 24 complete frozen prediction fields; **16** original-result Champion/CORE-004 pairs; **14** same-race normalized WIN triples and **2** without qualifying WIN. 30 triple target **not yet reached**. | **OPERATIONALLY_VERIFIED** benchmark; limited sample, not a calibrated edge |
| **M2 – PIT attestation** | **0** independently PIT-certified physical races. 4 Nov Jägersro `RIKSTOTO:S3_NR_2026-11-04:5` 20:26 T−4 (if unchanged), existing 22:15 after-audit. Morning 9 active and 9 TMP identities. No later result can repair missing prestart identity or scratch original. | **BLOCKED_SOURCE**, no retrospective certification |
| **M3 – Cumulative coverage** | Authenticated DEV011 sources still incomplete; five older model artifacts are present but unindexed, one original `S2_NR_2026-11-03:8` result conflict; expiry may destroy source bytes. `#134` targets transient paging outages, `#133` improves observability. | **PARTIAL / BLOCKED_SOURCE**, long-term storage **BLOCKED_INFRASTRUCTURE** |
| **M4 – V1 system integrity** | Main audit [41820373324](https://github.com/Maremoo2/Betting/actions/runs/41820373324): temporal PASS; **five** runtime replay mismatches `combined_probability_mismatch` and `conflict_score_mismatch`; **one** overdue unsettled Skive shadow ticket issue [#82](https://github.com/Maremoo2/Betting/issues/82); provider WARN **14/15015** failures (12 letrot, 2 Rikstoto). Original source replay suggests legacy late-attached provenance, but never rewrites old decisions or converts FAIL to PASS. | **FAIL / BLOCKED_SOURCE**, no fake settlement |
| **M5 – Multi-leg** | Existing #129 probability-only independent combination/system hit probability and original Bjerke/Axevalla 3 Nov composite `X1_NR_2026-11-03#V4#4`. No fully time-qualified pool joint combination price, takeout, payout/dividend rules and four eligible freeze reports. | **PARTIAL / EV_BLOCKED_SOURCE** |
| **M6 – 13 Nov MVP acceptance** | Full new benchmark and archive observability are progressing, but independent PIT = 0, V1 audit FAIL and source coverage incomplete. `bet_authority=false` throughout. | **NOT_ACCEPTED** as real-money/economic EV system |

**Priority / next three:** (1) owner review sequential #134 → #133; check combined original CI and then health/archive #135/#136, **never merge without explicit user consent**; (2) preserve 4 Nov scheduled Jägersro T−4/PIT audit; (3) close V1 Skive/result-code and original identity gaps through externally verifiable sources, not by policy or source-contract relaxation. No new Champion, CORE004, V3.3.12, BET/WATCH/PASS, pricing, stake, historical decision, T−4 or PIT-003A rule changes. Local storage is not production retention.


## MVP-016 | Prospektiv forskningsplattform – 4. november 2026 (nyeste snapshot, PR-review)

**Kilde:** [Originalbasert MVP-016 revisjon](MVP016_RESEARCH_PLATFORM_ORIGINAL_EVIDENCE_20261104.md), ordinær CORE-003-kjøring [41814068321](https://github.com/Maremoo2/Betting/actions/runs/41814068321), **fire** eksakte originaler og SHA-256. Start-main `054dd26c5cfdaaf03219222ead25364b7a0ad915`. Status under denne teksten er historiske snapshots, ikke omskrevet. Frist **13.11.2026 18:00 Europe/Oslo**. Ingen automatisk merge.

| Leveranse | Kodestatus | Kildemåling / faktisk aksept |
| --- | --- | --- |
| DEV-013 originalbasert WIN-evaluering | **OPERATIONALLY_VERIFIED** på main | 4.11 ordinær kjøring: **63 unike fysiske løp** (fra 59), **16** originalutfall-scorede Champion/CORE-004-par, **14** samtidige WIN-triples, **2** uten WIN, **0** PIT; 24 komplette modellfullfelt, men ikke 24 verifiserte resultater |
| MVP-016 / PR #132 no-op-arkivindeks | **CODE_COMPLETE / CI_PASS / PR DRAFT** | Ekte 4.11 no-op-original med SHA `ebeb64f1…`: null nye løp, null feilaktige arkivfeil. **12** falske no-op-indeksavvisninger i dagens main-scorecard blir riktig skilt fra korrupte originaler etter fremtidig owner-godkjent merge |
| MVP-016 / PR #133 research coverage V2 | **CODE_COMPLETE / PR DRAFT – CI/operativ sidecar må bekreftes på eksakt HEAD** | En egen original-joinet, maskinlesbar matrise per fysisk løp, avvisningsårsaker, per bane/dag, alternative SHA-frys og parvise feil med eksplisitt få-observasjoner-status. Ingen ny modell og ingen ekstra PIT/BET |
| Faste prospektive datakrav | **BLOCKED_SOURCE** | Dagens CORE-003 F2 #3/#4: **2** løp, 9+11 morgenaktive, 0 komplett uavhengig ATG-fundamentalfelt og 0 kvalifisert WIN; TMP-identiteter. Ikke tell disse som 2 nye scorede løp |
| DEV-011 arkivretensjon | **PARTIAL / BLOCKED_INFRASTRUCTURE for ny langtidslagring** | 30 GitHub inventarsider/2950 entries, 181 gjenvunnet, 5 ekte legacy modeller er **UNINDEXED**, 1 konfliktende offisiell resultatkvittering, `coverage_complete=false`. Ny append-only privat lagringsdestinasjon/tilgang/retensjon **ikke autorisert eller verifisert**, derfor ikke implementert |
| V1 replay / Skive #82 | **BLOCKED_SOURCE / INTEGRITY FAIL** | Main audit [41796687537](https://github.com/Maremoo2/Betting/actions/runs/41796687537): temporal PASS, runtime replay FAIL (5 eldre), settlement FAIL (1), provider WARN. Ingen historisk omskriving, falsk settlement eller audit-waiver |
| Jägersro MVP-011 | **BLOCKED_SOURCE, PIT=0** | Planlagt T−4 20:26 og eksisterende 22:15-etterkontroll 4.11 Oslo. Morgen 9/9 felt, 9/9 `TMP`-ID, ingen uavhengig krysskildesertifisering. Ingen duplikatautomasjon |
| V4X / V75 / V85 | **PARTIAL forskningskode / BLOCKED_SOURCE EV** | Fysisk V4X-originalidentitet funnet og generisk kombinasjonssannsynlighet merget i #129. Mangler SHA-/tidsgyldige felles kombinasjonspriser, system-/jackpot-/takeout- og offisielle oppgjørsregler, samt fire fullstendige modellfrys. Ingen V4X-EV eller spill |

**Prioriterte tre neste handlinger:** (1) Godkjen og test PR #132/#133 separat, deretter mål på ordinær main etter en eventuell merge; (2) bevar originalt Jägersro T−4 og allerede planlagt uavhengig PIT etterkontroll; (3) jobb fra originalene med V1-replay/Skive-integritet og ny prospektiv kildeidentitet fremfor å bruke senere odds eller konstruert fleravdelings-EV.

**Absolutt:** Champion V1.1, CORE-004-vekter, V3.3.12, T−4/PIT-003A, BET/WATCH/PASS, innsats, historiske beslutninger og `bet_authority=false` er uendret. Modellfordel eller kalibrering ved 14 triples kan ikke erklæres.


## MVP-014 – 4. november: post-merge originals and legacy coverage diagnosis

**Append-only read-only status**, not a retrospective change to earlier audits. [Full SHA-verified evidence](MVP014_20261104_LEGACY_ORIGINAL_INDEX_ROOT_CAUSE.md). Main at this control: `254ae4b5ec6c5e97622a1881b581e9c7d9c86f9b`. Owner has already merged PR #128 (DEV-013) and #129 (V4/V75/V85 probability-only research). No new merge authority.

| Priority | Current factual status | Next acceptance |
| --- | --- | --- |
| P0 DEV-013 | **DONE code / CI_PASS / PARTIAL operations** – scheduled 4 Nov 08:07 and 08:17 Oslo executions skipped actual source/model/scorecard steps under hours gate; last real cumulative before merge remains 59 unique race IDs, 10 scored pairs, 0 simultaneous WIN triples, 0 PIT; DEV-013 original PR replay verified eight triples for fixed eligible earlier cohort | First **actual executed** post-merge scheduled CORE-003 scorecard with original SHA/timestamps, no after-the-fact selection |
| P0 DEV-011 cumulative source quality | **PARTIAL:** last nonempty 2692 GitHub entries, 27 pages, 151 indexed artifacts, 10 pinned results, one conflicting official result. All five earlier 'missing' GitHub model artifact IDs **are actually downloadable**, but have unindexed legacy `shadow.json` layouts; this isolated PR improves blocker classification only | Report five `UNINDEXED_LEGACY_MODEL_ORIGINAL` as still BLOCKED, do not admit them or change historical denominator |
| P0 Jägersro / MVP-011 | **BLOCKED_SOURCE:** Collector 4 Nov morning original has 9/9 race 5 active, full PDF/startlist consistency, **9/9 TMP registration identifiers**, no independently attested cross-provider IDs; original source publication time not attested. T−4 ~20:26 Oslo today, original after-audit already scheduled 22:15 | Wait for actual future T−4 and complete independent identity/scratch receipts, preserve existing once-only review |
| P0 V1 integrity | **FAIL** from scheduled audit 41747967150: 5 replay mismatches, settlement ticket issue #82, provider warning 14; code CI GREEN does not satisfy this | Separate immutable official adjudication; no policy/settlement rewriting |
| P1 DEV-014 V4X | **PARTIAL / BLOCKED_SOURCE economic EV**: original physical composite pool mapping documented, but no verified joint pool pricing/takeout/jackpot/payout and no valid full frozen model on all four legs | Continue after P0, no WIN-for-pool-price substitution |

**Research/BET status:** `bet_authority=false`; no PIT-003A, Champion, CORE-004, V3.3.12 or wagering rule changes. 13 Nov 18:00 Europe/Oslo target unchanged.


## MVP-014 – BULK EXECUTION snapshot, 3 November 2026 (append-only, unmerged review)

**Proposed research-only roadmap update from [MVP-014 source audit](MVP014_BULK_EXECUTION_SOURCE_AUDIT_20261103.md).** Main baseline `4047fdee0984b4289b1ef86797f894b8d0227da0`. Source: original GitHub CORE-003 and Collector archives. This section is a new time-scoped snapshot; legacy audits and decisions below remain immutable. Frist **13.11.2026 18:00 Europe/Oslo**.

| Workstream | Status | Verifiable acceptance boundary |
| --- | --- | --- |
| DEV-009 | **DONE technical / PARTIAL evidence** | Original scorecard has 10 distinct official-result-scored Champion/CORE-004 pairs, no independent PIT; the current main WIN benchmark still has zero complete triples |
| DEV-010 / MVP-011 PIT | **BLOCKED_SOURCE** | Independently certified races **0**; existing once-only Jägersro Nov 4 22:15 audit remains enabled, cannot act before real T−4 |
| DEV-011 / PR #126 | **DONE code / PARTIAL cumulative coverage** | Latest nonempty scheduled run 41716853961: 2692 GitHub artifact entries/27 pages, 151 recovered, 10 pinned original outcomes, five unavailable model artifacts and one conflicting official result |
| DEV-012 / PR #127 | **DONE code / CI_PASS / PARTIAL operations** | Six original PDF continuation races verify with merged fixed parser. No subsequent ordinary completed model cohort demonstrates new admission from these cases |
| DEV-013 / PR #128 | **CI_PASS / BLOCKED_IMPLEMENTATION pending owner decision** | Draft HEAD `19f9eff2ea814ecce5b8013065e3728e52357dbd`; 1504 passed, 78 skipped, authentic Eskilstuna triple replay, expected 10 original pairs/8 triple in controlled offline sample; NOT verified operationally on main |
| MVP-012 / MVP-013 | **PARTIAL** | Operational 59 cumulative race IDs, 10 model/result pairs; sample 41 original 3 Nov run indexes shows 16 unique race IDs/2 model-frozen/14 source-rejected; no PIT |
| DEV-014 / MVP-014 V4X | **PARTIAL / BLOCKED_SOURCE for system EV** | Verified original composite pool key `X1_NR_2026-11-03#V4#4`, physical S2#8, BJ#7, S2#9, BJ#8. Missing prospectively verifiable collective joint combination prices, ticket/dividend/pool rules and two model freezes; no EV |
| P0 V1 replay and Skive #82 | **BLOCKED_SOURCE / INTEGRITY OPEN** | Five older replay mismatches, unsettled original Skive evidence, five unavailable model archives, one conflicting S2#8 official outcome; no audit waiver |
| Betting activation | **OFF** | `bet_authority=false`; no real-money or autobet authority; Champion/CORE-004/V3.3.12/hardgates unchanged |

**Three next decisions:** (1) owner review #128 and if approved prove next ordinary main triple coverage; (2) preserve Jägersro PIT audit; (3) after P0, obtain original V4X source economics before any joint EV. No model fitting or historical backfill. This roadmap change is itself a draft PR pending review, not an accepted `main` status until owner merge.

## MVP-010 – operativ kilde- og PIT-attestasjon, 3. november 2026

**Aktiv nyeste status; tidligere MVP-009/-008-seksjoner beholdes som historiske snapshots.** Eksakt kode-HEAD ved oppstart og verifikasjon: `de527509a28ce62d49ef466ecc540bf927230039` (merget PR #124). Denne dokumentasjonsendringen alene gir ikke PIT/BET-autoritet. Frist 13.11.2026 18:00 Europe/Oslo.

| Chunk | Reelt funn og status | Originalt bevis | Neste tiltak |
| --- | --- | --- | --- |
| **A – operasjonell main: MERGED_AND_OPERATIONALLY_VERIFIED** | [Main CI 41645107876](https://github.com/Maremoo2/Betting/actions/runs/41645107876) **PASS**, Ruff + 1463 passed / 74 skipped. [V1-integritet 41645107740](https://github.com/Maremoo2/Betting/actions/runs/41645107740) **PASS** på clean research-db. [Provider live-smoke 41645107041](https://github.com/Maremoo2/Betting/actions/runs/41645107041) **PASS** på merge-HEAD. [V1 canonical system audit 41645107156](https://github.com/Maremoo2/Betting/actions/runs/41645107156) **FAIL** på restaurert historisk state: fem eldre replay-mismatch (346 vurdert, 527 skipped), én overfrists ikke-oppgjort shadow-kupong (871 kontrollert); temporal PASS, provider WARN med 14 fetch-feil. IKKE en attestasjon av V1 P0 PASS. | CORE-003 [push-run 41645107027](https://github.com/Maremoo2/Betting/actions/runs/41645107027) PRODUSERTE `mvp009-decision-audits-41645107027` (artefakt 13234627321). **Viktigst:** ordinær **schedule-run [41646155051](https://github.com/Maremoo2/Betting/actions/runs/41646155051) PASS** på samme HEAD, med `mvp009-decision-audits-41646155051` (artefakt 13234034817), 1/1 modell, 12/12 aktive, WIN 12/12, gyldig modell-/attest-SHA-kobling, alle BLOCKED, null BET; diagnostikk indeks SHA256 `4f419d94ccfa9b5df5626c7f0d65854fab1a8582ce2978b1d41370cbd2ca8395`. | **Chunk A DONE teknisk + operativt.** Eldre V1 P0-avvik forblir røde, separat fra PIT. Ingen ny PR eller workflow dispatch. |
| **B – Jägersro: BLOCKED_SOURCE_IDENTITY** | Fysisk løp `RIKSTOTO:S3_NR_2026-11-04:5` er i originalt prospektivt CORE-003-SQLite-løpsregister. Råparset Rikstoto-kalender observert senest 2026-11-03T13:32:11Z: start **2026-11-04T19:30Z = 20:30 Oslo**, ved uendret klokke T−4 20:26. Skjema markerer imidlertid kalenderbeviset `HASH_ONLY_NO_RAW_BYTES`, `pit_verified=0`. **0** originalbaserte fullfelt hesteidentiteter attestert. Eksterne startlister viser 9 kandidater, ikke attestert aktivt originalfelt; ingen Sportinfo→ATG→Rikstoto råkilde-ID-proveniens. | Isolert `core003-pilot-state` fra 41645107027, artefakt 13233849825: `provider_race_refs`/`race_schedule_observations`; ingen `runner_fundamental_snapshots` eller `provider_payloads` for denne starten ved kontrollen. Offisielt Svensk Travsport løpskalender bekrefter meetingdag; 3.-part oppført ni løpere er ikke krysskildebevis. | Skaff original Svensk Travsport-startliste med stabile profil-ID-er og rå SHA/observasjonstid, ATG `horse.id`, Rikstoto `/starts`/`/scratched` og original PDF for samme løp før as-of/T−4. Hvis ingen råkildekobling: behold sperren og gå til offisielt bekreftet Halmstad 7.11. |
| **C – strykestatus: BLOCKED_SOURCE** | Ny original fra **løp 8** 3.11 13:41:02Z viser på nytt `/scratched` HTTP200/success=true, bare nøkler `2,3,4`, mens `/starts` løp8 oppgir **12/12 isScratched=false**. Rå `/scratched` SHA `1273a06752f5424480f729d256279ea649860d94ac096dcc6d4c3c42a001587a`; dette bekrefter konsistens over to observerte T−4-løp, **ikke** autoritativ kontrakt for manglende nøkkel. | [Schedule-run 41646155051](https://github.com/Maremoo2/Betting/actions/runs/41646155051), `pit003a-source-receipts-41646155051` artefakt 13235705644 med 3 rå JSON + SHA og tidsklokker. | Mangler offisiell Rikstoto-definisjon av fraværende løpsnøkkel (=0 vs unknown/not published/incomplete). Behold streng `UNVERIFIED_SCRATCH_SOURCE`; ingen parserendring. |
| **D – første PIT: PIT_NOT_CERTIFIED** | **Ny reell T−4-attestasjon** for fysisk Eskilstuna løp8, start 2026-11-03T13:46:00Z, T−4 13:42:00Z. Original kildeobservasjon: racedays 13:41:01.186668Z, starts 13:41:01.839413Z, scratched 13:41:02.395794Z. Modell fryst 13:41:11.103257Z, SHA `f04dd8f19254764114739009383371e3367c445c917c8fac5b08cf085e814a6d`. PIT join **1 vurdert, 0 sertifisert**. Eksakt attestasjonsblokkering: `STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED` + `UNVERIFIED_SCRATCH_SOURCE`. Kildens opprinnelige publiseringstid ikke oppgitt. | [Schedule-run 41646155051](https://github.com/Maremoo2/Betting/actions/runs/41646155051), `pit003a-attestations-41646155051` artefakt 13235715717; original T−4 receipts artefakt 13235705644; fryst modell artefakt 13235845295, diagnostikk artefakt 13234034817. | Innhent offisiell fullfelt ID-kjede og autoritativ scratchstatus for ett og samme fysisk framtidig løp, bevart tidsriktig; først da kan eksisterende PIT-hardgates forsøkes fullt. Ingen syntetiske bevis eller sen-kilder. |

**Nevner i ny ordinær run 41646155051:** tre løpsreferanser i fast kildekohort (Eskilstuna8 + to franske løp), **én** kildeverifisert og modellfrosset (12/12 hester, full WIN), to `COLLECTOR_RESEARCH_MODEL_GATE_NOT_VERIFIED`; **én** fysisk PIT-vurdert, **null** sertifisert. Ikke tell gjentatt push- og schedule-kjøring av Eskilstuna8 som to forskjellige løp. Jägersro 4.11 er kandidat, ennå ikke faktisk T−4-vurdert.

**Roadmap-beslutning:** Teknisk forskningsmotor, originalfangst, fryst modell/WIN, PIT fail-closed og automatiske GitHub-diagnostikker fungerer prospektivt. **MVP-010 er IKKE fullført**; første selvstendig godkjente PIT er fortsatt `0`. Ingen modell-/policy-/hardgate-endring, ingen merge, ingen produksjonsstate-writes eller dispatch i denne kontrollen; kun dokumentasjon er oppdatert.


## MVP-009 – prospektiv kildeverifisering og automatisk diagnostikk (3. november 2026)

**Gjeldende operative status; eldre MVP-008-/007-/005-seksjoner nedenfor beholdes som historikk.** Frist 13. november 2026 kl. 18:00 Europe/Oslo. Verifisert baseline ved oppstart: main `71724072e8879881ecbe8201b9c8110197340aad`. PR #122 og #123 er merget; de skal ikke implementeres på nytt.

| Chunk | Faktisk levert | Verifisert original / CI | Status og neste nødvendige handling |
| --- | --- | --- | --- |
| **MVP-009/1 – Jägersro 4. november** | Identifisert fysisk løp `RIKSTOTO:S3_NR_2026-11-04:5`, planlagt 20:30 Oslo; eksisterende Collector/CORE-003-pipeline klart for sin ordinære prospektive kjøring. Førstegangs PIT krever faktisk T−4 før 20:26 dersom starttid uendret. | Svensk Travsports løpskalender og offentlige V86-listinger, men ingen innhentet og tidsattestert original svensk startnummer→profil/ATG-ID→Rikstoto-kjede for hele aktive feltet; 9 fra tredjepart er kun foreløpig nevner. | **BLOCKED_SOURCE_IDENTITY** – 0 prospektivt godkjente hester. Verifiser originale svenske startlisteprofil-ID-er, ATG horse.id og Rikstoto raw starts/scratched via planlagt Collector før as-of; ellers kandidat Halmstad 7. november (offisiell kalender bekreftes ved bruk). Ikke navnebasert EXACT. |
| **MVP-009/2 – Rikstoto scratched** | Kontrollerte originale Eskilstuna-kildene og både gammel forskningsparser og streng PIT-parser. Ingen endring i parser eller gate. | [Run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709), raw /scratched SHA-256 `1273a06752f5424480f729d256279ea649860d94ac096dcc6d4c3c42a001587a`; success=true, løp 1 ikke oppført, starts 12/12 false. | **BLOCKED_SOURCE** – mangler autoritativ kontrakt for utelatt løpsnøkkel vs null/ukjent/ikke-publisert. Behold `UNVERIFIED_SCRATCH_SOURCE` og streng `_scratch_set()`. Ingen kodeoppgave før offisielt kildebevis. |
| **MVP-009/3 – automatisert read-only beslutningsdiagnostikk** | **CODE_COMPLETE / PR OPEN, IKKE MERGET.** [PR #124](https://github.com/Maremoo2/Betting/pull/124) gjenbruker merget `hbi.mvp008_decision_audit`; ny runner verifiserer frosne rapporters SHA/løps-ID, bevarer kildeindeks/attest-SHA og skriver eksklusiv per-løpsdiagnostikk. Eksisterende planlagt CORE-003-workflow kobles til upload etter PIT-attestasjon. | [CI 41640968602](https://github.com/Maremoo2/Betting/actions/runs/41640968602) **PASS**: Ruff, 1463 passed / 74 skipped, Collector originalreplay, pluss 10/10 originale Eskilstuna-regresjoner. GitHub-artefakt `mvp009-original-decision-diagnostics-41640968602` (ID 13232354202) ble faktisk generert og lastet opp. 2/2 originale fryste løp; Eskilstuna løp 1 12/12 aktive, komplett WIN, PIT-attest matches; løp 3 mangler attestasjonskobling; 0 BET. Original modell-SHA løp 1 `4853ed6bc8c7c7063a5898f4b815e552989d29d9b3121372fd338eb0e63f9916`. | **Neste tekniske PR til eiervurdering: #124.** Samlet PR-check er IKKE helgrønn: [HBI Provider Live Smoke 41640968680](https://github.com/Maremoo2/Betting/actions/runs/41640968680) FAIL med `NO_FULL_FIELD_LIVE_PASS:FR`; [main Live Smoke 41638471333](https://github.com/Maremoo2/Betting/actions/runs/41638471333) hadde PASS ca. 18 minutter tidligere da FR Nantes-løp 3 hadde fullfeltsdekning. Dette er variabel ekstern FR-dekning, ikke en dokumentert endring i provider-koden fra PR #124; kildekontrollen kan ikke forties. Kun eier kan godkjenne merge. Prospektiv produksjon av nytt *planlagt* CORE-003-artefakt må bekreftes i en ordinær fremtidig kjøring etter eventuell merge; PR CI er ekte originalreplay, ikke framtidig PIT. |
| **MVP-009/4 – første uavhengige PIT** | Eksisterende PIT-sidecar og source-gates uendret; Eskilstuna 3/3 T−4-kilder og 1 gjennomført attestasjon er verifisert, **0 sertifisert**. | Original [run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709). | **PIT_NOT_CERTIFIED**: to konkrete gater – `STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED` og `UNVERIFIED_SCRATCH_SOURCE`. For et nytt fysisk løp kreves autoritativ fullfeltsidentitet + strykestatus, tre rå SHA, klokker før cutoff, uavhengig Collector-versjon, modellfrys og entydig attestasjonsjoin. Ingen backdating. |

**MVP-konklusjon:** Originalfangst, isolert SQLite, Champion/CORE-004 og WIN fungerer i prospektiv forskningsmodus; GitHub CI demonstrerer nå dessuten helautomatisk avledet diagnostikk fra autentiske fryste originaler på PR-HEAD. Kodeintegrasjon til planlagt forskning er **ikke på main** før eiermerget PR #124. Full PIT og kvalifisert V3.3 BET/WATCH/PASS er **ikke** levert: uavhengig identitet, autoritativ scratched-kilde og senere kalibrering/FFQ-1/preregistrert batch mangler. `bet_authority=false`. Ingen nye modeller, odds-/innsatsregler eller produksjonsstate er endret.

## MVP-008 – leveranseorientert status 3. november 2026

**Dette er gjeldende fremdriftsstatus; eldre MVP-007/MVP-005-tekst nedenfor er historisk.** Dokumentasjon endrer ikke frosne strategier eller PIT/BET-hardgates.

| Chunk | Teknisk leveranse | Bevis | Eksakt gjenværende sperre |
| --- | --- | --- | --- |
| **008A / strykekontrakt – BLOCKED_SOURCE** | Original Eskilstuna T−4-/scratched og begge eksisterende parsere revidert; source-limitation fastslått | [CORE-003 run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709), pit003a-source-receipts, original scratched.raw.json SHA-256: 1273a06752f5424480f729d256279ea649860d94ac096dcc6d4c3c42a001587a | Rikstoto svarte success=true med kun løp 2,3,4 som nøkler; løp 1 mangler. /starts rapporterer alle 12 med isScratched=false, men offisiell kontrakt for manglende løpsnøkkel kontra null/ukjent/ikke publisert ble ikke funnet. Streng _scratch_set() må fortsette å returnere unknown; eldre research _scratched_for_race() sin tom-mengde-antakelse er ikke PIT-bevis. |
| **008B / svensk identitet – BLOCKED_SOURCE_IDENTITY** | Eksakt fysisk kandidat identifisert: Jägersro 4. november kl. 20:30, RIKSTOTO:S3_NR_2026-11-04:5; offentlig forhåndsliste viser 9 hester | Offentlig V86-startliste, men ingen komplett tidsattestert original-ID-kjede bevart | 0/9 av de foreløpig oppførte er prospektivt attestert; 9 er **ikke** verifisert aktivt originalfelt. Original Sportinfo/Svensk Travsport startnummer→stabil ID, ATG horse.id og Rikstoto-kryss, rå SHA og as-of mangler. Alternativ kandidat: Halmstad 7. november (reverifiser først). |
| **008C / modell til beslutningsdiagnostikk – IMPLEMENTERT, PR OPEN** | [PR #123](https://github.com/Maremoo2/Betting/pull/123) gir read-only diagnostikk for alle aktive hester, Champion p(win), teoretisk fair odds, CORE-004 research, WIN, normalisert marked, ukalibrert teori-EV og per-hest manglende V3.3-kontrakter. Eksklusiv output, ingen BET. | PR HEAD e2aceafd5853fcda55553ea879b239791bcfc432; [CI 41637151141](https://github.com/Maremoo2/Betting/actions/runs/41637151141) Ruff PASS, 1454 PASS / 73 SKIP, autentisk Collector-arkivreplay PASS. Separat lokal kontroll mot Eskilstuna-originalmodell SHA-256 4853ed6bc8c7c7063a5898f4b815e552989d29d9b3121372fd338eb0e63f9916 viser **12/12 aktive og 12/12 WIN**, alle BLOCKED; 17 lokaltester PASS, én valgfri originalartifakt-test SKIP i vanlig CI. | Original kildeidentitet og strykestatus, PIT, kalibrerte p_low/p_mid/p_high, FFQ-1, minstepriser og preregistrert V3.3 batch er ikke tilgjengelige. V3.3-evaluering ikke kalt; PR ikke merget; bet_authority=false. |

**Eskilstuna T−4-fasit:** [run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709) fanget 3/3 originalresponser før T−4, modell og WIN 12/12. Én faktisk fangst, én vurdert attestasjon, **null sertifiserte**. De eksakte sperrene fra PIT-index er STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED og UNVERIFIED_SCRATCH_SOURCE. Grønn CI er ikke lik PIT PASS.

**Neste operative P0 handling før MVP-frist 13. november 2026 18:00 Oslo:** Sikre en offisiell, original og tidsriktig fullfelts startnummer→registrering/Sportinfo→ATG horse.id→Rikstoto-kjede og separat dokumentert scratch-kontrakt (inkludert null/ukjent/ikke publisert). Prøv Jägersro 4. nov; hvis den eksterne originalen ikke er tilgjengelig, velg Halmstad 7. nov. Tilfør ingen kode eller PASS som omgår kildesperrer. Første INDEPENDENT_PIT_CERTIFIED krever alle samtidige kilde- og modellavstemminger; verken kodeleveranse eller observasjon alene gir BET-autoritet. Eneste nye DEV-PR er #123 for diagnostikk; eieren bestemmer eventuell merge.



## MVP-007 – operativ status 3. november 2026 (oppdatert etter PR #122)

**Dette er nyeste status; eldre daterte MVP-005-/30. oktober-punkter nedenfor er historiske.** Ingen PIT-/BET-gate er endret.

- **DEV-007A: DONE / MERGED.** [PR #122](https://github.com/Maremoo2/Betting/pull/122) ble merget 2026-11-03T11:59:53Z, merge-commit `741d927e664b25e183256613c2b7c7f83d69f27d`. Eneste programvareendring er korrekt CLI-telling av `results` ved `attest` (fortsatt `records` ved `capture`), pluss seks regresjonstilfeller. [PR-CI](https://github.com/Maremoo2/Betting/actions/runs/41631306721): Ruff PASS, 1437 passed / 72 skipped, original-Collector replay PASS.
- **Eskilstuna løp 1 (2026-11-03):** [CORE-003/T−4-run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709) dokumenterer 3/3 originale kilder før T−4, WIN 12/12 og begge forskningsmodeller `MODEL_READY`; én faktisk fangst og én vurdert attestasjon, **0 PIT-sertifiserte**. Kildeblokker: `STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED` og `UNVERIFIED_SCRATCH_SOURCE`. Rikstoto `/scratched` manglet eksplisitt løp 1; ikke tolk dette som verifisert tom liste.
- **Neste P0-kandidat:** Jägersro 4. november 2026 løp 5 kl. 20:30 Oslo (`RIKSTOTO:S3_NR_2026-11-04:5`). Offentlige tredjepartsoversikter viser foreløpig ni hester, **ikke en attestert original fullfeltnevner**. Svensk Travsport-startliste med originale profilreferanser, rå Sportinfo/ATG/Rikstoto-identiteter, endringer/strykninger og før-as-of SHA-/klokkebevis er ennå ikke dokumentert.
- **Prioritert handling:** Fullfør originalbasert, tidsriktig identitet for samtlige aktive hester; dokumenter offisiell semantikk for manglende løpsnøkkel i `/scratched`; kjør eksisterende strenge PIT-attestasjon uten backdating eller endrede hardgates. Hvis bevis mangler: `BLOCKED_SOURCE_IDENTITY` / `PIT_NOT_CERTIFIED`, aldri falsk `PASS`.
- **Teknisk MVP-beslutning:** 13. november 2026 kl. 18:00 Oslo. Prospektiv forskningskjede demonstrert, men uavhengig identitet, strykestatus og PIT fortsatt ikke godkjent; `bet_authority=false`. Ingen ny kodeoppgave uten en konkret kildebevist implementerbar feil.

## MVP-005 – gjeldende styring og MVP-kritisk sti (3. november 2026)

**Dette er den gjeldende beslutningen for neste steg og erstatter tidligere administrative reviewkrav i eldre, daterte avsnitt nedenfor.** Prosjekteieren er eneste autoriserte mergebeslutter. Ekstern godkjenner, `HQ_REVIEWER_LOGINS`, `APPROVED_FOR_MERGE`-kommentar og obligatorisk branch protection er **ikke** lenger krav. Ingen merge uten uttrykkelig tillatelse fra eieren. Full teknisk kildeintegritet, originale hash-bevis og alle PIT/BET-hardgates beholdes.

### Oppnådd mot MVP

- **MVP-INTEGRATION-003:** Autentisert Collector-original → kildehash-verifisert SQLite med unike per-løp-poster, readback og idempotens; `TMP` og manglende uavhengig identitet gir fortsatt streng modell-/PIT/BET-blokkering.
- **MVP-INTEGRATION-004:** Ekte, historisk Halmstad løp 10 (2. november) har importert original PDF og `/starts`, vurdert 8/8 entydige ATG-navn/startnummer og kjørt uendrede Champion/CORE-004 på nytt fra isolert SQLite. Begge p(win)-summer er `1.0`, `MODEL_READY`, `HISTORICAL_REPLAY`, `research_model_eligible=true` og `independent_identity_attested=false`. `pit_certified=false`, `bet_authority=false`. Bevis: https://github.com/Maremoo2/Betting/actions/runs/41605276615 og immutable `mvp004-historical-research-41605276615`-artefakt.
- Teknisk CI på den historisk beståtte PR-HEAD `0a629a8d794af5c1a1d68e68ede14aa68990e59e`: Ruff PASS, 1 431 tester PASS / 72 SKIP; `v1-integrity` PASS; `protected-strategy` PASS. **Dette må bekreftes på ny HEAD etter administrative dokument-/workflowendringer.**
- Uavhengig GitHub-review var en **administrativ** rød gate. Den er ikke lenger et gjeldende akseptkrav etter eiers beslutning. Dansk `NO_FULL_FIELD_LIVE_PASS:DK` forblir rød, og danske løp var ikke faktisk forsøkt i sammenlignede live-smoke-kjøringer; ingen dansk datadekning er påvist. Denne separate diagnostikken er ikke automatisk Collector-mergeblokker uten et uttrykkelig DK-dekningskrav.

### Datoer, eierskap og aksept

| Frist (Europe/Oslo) | Leveranse | Status / aksept |
| --- | --- | --- |
| **4. november 2026** | PR #121: fjern administrativ HQ-gate, oppdater roadmap, verifiser **ny eksakt HEAD**, CI, kildeintegritet og uendret PIT/BET-kontrakt | DEV leverer bevis; eieren avgjør merge |
| **6. november 2026** | Betinget merge til `main` | **Kun ved uttrykkelig eiersamtykke**, PASS på relevante automatiske tekniske kontroller, ingen sikkerhetsregresjon; ellers `BLOCKED` |
| **10. november 2026** | Første egnete prospektive norske/svenske løp med autentisert Collector-original og fullt ATG-felt | Etter eventuell merge: verifiser fysisk løp, hester, strykninger, kildeversjon og originaler før modell `as-of`; kjør uendrede modeller; attester T−4 uavhengig; rapporter `PASS`, `BLOCKED` eller `NOT_OBSERVED` |
| **13. november 2026 kl. 18:00** | Teknisk MVP-beslutning | Fungerende prospektiv kjede og faktisk PIT-evidens, eller konkret dokumentert `BLOCKED` med første feil/observasjonsmangel. **Ingen BET-autoritet automatisk.** |

### Roller og beslutningsregler

- **Roadmap/HQ:** undersøk nøyaktig PR-head og alle statuskontroller; klassifiser tekniske feil kontra separat leverandørdekning; hold kritisk sti og datert bevis oversikt. Ikke opprett nye prosesser eller sideprosjekter.
- **Betting DEV:** bare nødvendige feilrettinger når konkrete tekniske blokkeringer er bevist. Ingen ny modell, ny arkitektur, endring i Champion/CORE-004/V3.3.12, innsatsregler eller hardgates.
- **Prosjekteier:** autoriser merge etter faktisk teknisk aksept. Branch protection/ruleset er frivillig. Det kreves ingen andre menneskelige reviewers.
- **Prospektiv PIT:** Collector-morgenprogram (planlagt kl. 07:00) er ikke alene T−4-bevis. GitHub cron kan være forsinket; observer faktiske kildeklokker. Ingen historisk replay eller syntetisk attest gir prospektiv sertifisering.
- **Risiko:** Høy for 13. november: prospektiv T−4-innsamling, ekte versjons- og publiseringsbevis og ATG-dekning er ikke bevist som ferdig. Hvis observert men utilstrekkelig, bruk `BLOCKED`; hvis ikke observert, bruk `NOT_OBSERVED`. Ikke erstatt med teoretisk grønn status.

**PR under arbeid:** https://github.com/Maremoo2/Betting/pull/121. **Denne roadmap-oppdateringen autoriserer ikke merge, autospill, workflow-dispatch eller bet.**

---

### Historisk roadmap (30. oktober; eldre administrative reviewkrav er foreldet)

**Rapportdato:** 30.10.2026 · **Modus:** GITHUB_REVIEW_AND_SOURCE_EVIDENCE_ONLY · **Betting:** OFF/ikke autorisert.

Dette er én samlet oversikt over oppnådd **kodeleveranse** versus faktisk **funksjonell akseptanse**. En merget PR, grønn GitHub Actions-kjøring eller simulatorresultat gir aldri i seg selv produsert PIT-bevis, kalibrert modelledge, gyldig oppgjør eller BET-mandat.

> **Oppdatering 30.10, senere kildekontroll:** [PR #92](https://github.com/Maremoo2/Betting/pull/92) har full CI PASS (**1167 pass / 47 skip**) og offisielt start-/strykningsbevis [run 41123773696](https://github.com/Maremoo2/Betting/actions/runs/41123773696). Alle fire Rikstoto GETs er HTTP 200; #8 finnes én gang blant 12 startlisterader, `isScratched=false`, og er **ikke på strykningslisten**. Resultatet forblir `place=0`/`kmTime="0,0"`; **start i selve løpet og gyldig tap er fortsatt ikke sikkert attestert**, ingen -25 NOK bokføring. [PR #93](https://github.com/Maremoo2/Betting/pull/93) stopper tilsvarende *forskningsmodell*-tidslekkasje i CORE-004; [pinned E2E 41124166985](https://github.com/Maremoo2/Betting/actions/runs/41124166985) PASS, mens ekstern Provider Live Smoke rapporterer selvstendig kildeblokkering. **PR #91/#92/#93 ikke merget på tidspunktet for denne oppdateringen.**


## Oversikt

| ID | Arbeidsstrøm | Kode integrert på main | Virkelig testet | Funksjonell milepæl | Neste obligatoriske akseptanse |
| --- | --- | --- | --- | --- | --- |
| **CORE-001** | Enkeltløp fullt felt | JA (#72, #80) | Fullfelt-, odds- og historiesjekker i isolert prøve | **BLOCKED** | Minst ett uavhengig PIT-attestert fysisk løp med publiserings- og klokkehistorikk og riktig originalt aktivt felt; [#89](https://github.com/Maremoo2/Betting/issues/89) |
| **CORE-002** | Hele racedays | JA (#72/#73/#80) | 9/31 eldre dag, 108/15 råkildeklar, **0/108 PIT** i arkivdelmengde | **BLOCKED** | Prospektiv race-day nevner, alle løp per land/bane, kildemangel og terminalstatus, uten etterpåklokskap; [#89](https://github.com/Maremoo2/Betting/issues/89) |
| **CORE-003** | Prefetch, identitet, historikk, T−4 | JA (#75–77, #80) | Shadow-piloter og original SQLite/kildehash. **Romme løp 8 30.10: 29 min klokkekonflikt**, post-ATG-start WIN-pris | **SHADOW, IKKE PIT-GODKJENT** | [PR #87](https://github.com/Maremoo2/Betting/pull/87) retter og [arkiv-E2E 41123151739](https://github.com/Maremoo2/Betting/actions/runs/41123151739) beviser **1/6→0/6** konservativt; review/merge, immutable rosterrevisjoner og kildens publiseringstid; [#83](https://github.com/Maremoo2/Betting/issues/83) |
| **CORE-004** | Multifaktor treningsgrunnlag | Research stub MERGET (#78) | Source-gate og syntetiske tester | **UFITTET, IKKE VALIDERT** | Verifiser last-five/klasse/kusk/distanse, tidsriktig markedsløs lineage; tren kun PIT-kronologisk uten OOS-lekkasje; [#90](https://github.com/Maremoo2/Betting/issues/90) |
| **P0-REPLAY-ENG** | Reproduserbar arkivreplay | MERGET #84/#85 | **REAL HASH-PINNED CLI PASS** [41116541999](https://github.com/Maremoo2/Betting/actions/runs/41116541999); **732 beslutninger, 321 WIN checks, 5/5 originalkilder** | **TEKNISK EVIDENS FULLFØRT** | [PR #86](https://github.com/Maremoo2/Betting/pull/86) review/merge av ikke-skriving workflow. Full kanonisk V1 audit fortsatt FAIL |
| **P0-REPLAY-INTEGRITY** | Historisk V1 replay | Diagnostikk MERGET | 305 combined replays, **5 mismatch** / 426 skip på separat auditstate | **FAIL/BLOCKED** | Uavhengig kildeadjudikasjon, godkjent append-only avklaring, aldri omskriv frosset proveniens eller gjør unntak i V1; [#81](https://github.com/Maremoo2/Betting/issues/81) |
| **P0-SETTLEMENT-SOURCE** | Skive 14.10 originalt resultat | Research-only source probe [PR #88](https://github.com/Maremoo2/Betting/pull/88) i REVIEW | **OFFISIELLE 2×HTTP 200** [41123021265](https://github.com/Maremoo2/Betting/actions/runs/41123021265), kildehash. Winner **#5**, Dividends **6,28**, valgt #8 med `place=0`, `kmTime="0,0"`, odds 31 | **ORIGINAL KILDE INNHENTET, DELTAKELSE BLOKKERT** | Primær/autoriserbar tolkning av #8 sin start-/stryk-/tapstatus og isolert regnskapsreplay; ingen -25 NOK nå; [#82](https://github.com/Maremoo2/Betting/issues/82) |
| **P0-SETTLEMENT-INTEGRITY** | Gyldig Shadow-bokføring | Original rutine finnes | Historisk åpen paper-kupong, **0** bokførte settlement-resultater for den | **FAIL/BLOCKED** | Original deltakelsesbevis, komplett resultat+dividende, korrekt idempotent replay, separat godkjent state write; [#82](https://github.com/Maremoo2/Betting/issues/82) |
| **P1** | Prospektiv markedsbaseline & kalibrering | Research-gate MERGET #80 | Eldre **297** retrospektive løp, combined minus market log-loss ca. **+0,0503** (svakere); ikke OOS | **NOT VALIDATED** | Godkjent og forhåndslåst framtidig par-design, minst 30 framtidige dager og statistisk testdesign, separat prediksjon/EV; [#90](https://github.com/Maremoo2/Betting/issues/90) |
| **OPERATIONAL** | Champion, BET, stakes | Frosset V3.3.12 | Kildestyrt Shadow/Pre-Watch, **ingen real-money tilstandsgodkjenning** | **OFF / IKKE AUTORISERT** | Alle hardgates + *separat* HQ betting-autorisasjon, aldri automatisk av kode-merge |

## Det som faktisk er fullført

- **#80, #84, #85** merget til main. Full repository PR #85-CI **1 150 PASS/47 SKIP** (ikke samtlige 1 197 testet).
- **P0 arkivbevis** med to låste originalhasher og faktisk GH-run; kilde SQLite uendret. Canonical runtime V1 **FAIL** selv om fem historiske originalkilder er rekonstruert. [PR #86](https://github.com/Maremoo2/Betting/pull/86) er review-only, ikke merget.
- **CORE-003 falsk positiv** er funnet i *samme opprinnelige seksløpsutvalg* og fjernet i PR #87, med uavhengig arkiv-GitHub-rerun [41123151739](https://github.com/Maremoo2/Betting/actions/runs/41123151739). 0/6 er en korrekt ærlig kontroll, ikke modellfeilretting.
- **P0 danske originalresultater** (HTTP 200 / response SHA-256) er hentet på GitHub runner, men hest #8 sin `place=0` og `kmTime=0,0` er *ikke* dokumentert som gyldig tapende deltaker. [#88](https://github.com/Maremoo2/Betting/pull/88) rapporterer BLOCKED selv om vinnerdividende er bevist.

## Kritisk sti for å fullføre *alle* funksjonelle milepæler

```text
P0 originalsettlement ─→ dokumentert #8-deltakelse ─→ isolert replay ─→ HQ state-approval
P0 legacy replay ─────→ kildeadjudikasjon ─→ immutable annotasjon ─→ canonical audit
CORE-003 PIT ─────────→ source clocks/roster/published-at ─→ CORE-001 PIT single race
                                                └──────────→ CORE-002 full racing days
CORE-001/002 PIT data ─→ CORE-004 feature lineage/training ─→ P1 preregistered OOS
[P0 clean + P1 proven] ─→ separat HQ-/risiko-/bettinggjennomgang; *ingen automatisk BET*
```

### Nå (kan utføres på ekte allerede)
1. Få #86, #87 og #88 gjennom nøyaktig GitHub-CI, uavhengig review og eksplisitt HEAD-bundet merge-godkjenning; ingen agent-merge.
2. Korriger **kildeklokkene i forskningsmetrikken**; skaff originalt ikke-prisbasert bevis for start-/strykestatus til Skive #8, og test idempotent oppgjør isolert uten skriverett.
3. Undersøk `LETROT_FULL_FIELD_CORROBORATION_FAILED` og `NO_PROVIDER_RACE` med original race-id/clock, og dokumenter dekning per land/dag, ikke ved å slakke på gates.
4. Gjennomfør *source lineage* og data-minimum for CORE-004 uten å trene eller evaluere på feilaktige T−4-felter.

### Senere (kan **ikke** løses sannferdig i ett møte)
1. PIT-publisering og versjonert startlistehistorikk må faktisk oppstå **før framtidige løp**.
2. Et prospektivt P1-eksperiment krever forhåndsgodkjent protokoll og nye kronologiske resultater over minst 30 dager. Dagens gamle resultater kan aldri gjøres til urørt OOS i ettertid.
3. Ingen BET eller kapitalinnsats før uavhengig P0-validering, kalibrering og separat godkjenning.

## Kilde- og tillatelsesgrense

**Original source:** GitHub Actions artifact/hash/SQLite og originale `RikstotoClient` HTTP response SHA. **Vår tolkning:** T−4-guard, kombinasjonsmodell, prospektiv kontrakt – forskningshypoteser, ikke garantert utbytte. **Brukerens egne prospektive resultater:** ikke tilgjengelige som kalibrert ROI-bevis.

`docs/DEV_WORKFLOW.md` krever eksakt PR-HEAD/HQ-review før merge; arbeidslisten gir ikke agenten merge-, scheduler- eller bet-autorisasjon. Originale gamle beslutninger og grunnkilden skal forbli uendret.

## 30.10 – korrigert fysisk løpsnevner (PR #99)

Den første heldagsrapporten ble beskrevet som 169 *fysiske* travløp, men den arkiverte kilden inneholder 15 `X1`-referanser over flere baner og 8 `S5`-referanser med `Solvalla/Bergsåker`. [PR #99](https://github.com/Maremoo2/Betting/pull/99) og original [GitHub-arkivkjøring 41127284420](https://github.com/Maremoo2/Betting/actions/runs/41127284420) skiller **169 database-referanser** fra **146 enkeltbane-kandidater** og **23 uavklarte kombinasjons-/lokasjonsreferanser**. Ingen av 146 er foreløpig individuelt sertifisert som unik fysisk start. De 23 beholdes synlige for kildekobling, ikke fjernet. Tidligere 17 foreløpig kildeklare og 0 PIT sertifiserte gjelder **alle 169 database-referanser**, ikke en godkjent fysisk løpsdekning.

## 30.10 – neste parallelle DEV-bølge (#94 og #95)

**CORE-003 heldagsdekning [PR #94](https://github.com/Maremoo2/Betting/pull/94)** – [faktisk GitHub archive-E2E 41125229029](https://github.com/Maremoo2/Betting/actions/runs/41125229029), JSON-artifact **13010796270**, SHA-256 `33febe452c4f8275507fd92106d5ef812ffb1bf2782a70bb62045e2b7e418823`, med opprinnelig HBI SQLite SHA-256 `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0`. **169** distinkte *arkiverte travløpsreferanser*, ikke verifisert fysiske løp (**146** enkeltbane-kandidater, **23** kombinerte/uavklarte), 27.–30.10, **167** etter T−4, **2** framtidige, **17** konservativt råkildeklare, **150** blokkert, **16** tidsavvik, **0 PIT-attesterte**. Første versjon Ruff F401 (ubrukt testimport), rettet; full re-run CI må kontrolleres særskilt. Det er **ikke** den samme kohorten som eldre 108-løpsaudit, så 17 mot 15 er ikke dokumentert dekningstrend.

| Land / status | Alle | Råkildeklare | Blokkert | Før T−4 |
| --- | ---: | ---: | ---: | ---: |
| Sverige | 77 | 17 | 60 | 0 |
| Norge | 24 | 0 | 24 | 0 |
| Danmark | 17 | 0 | 17 | 0 |
| Frankrike | 32 | 0 | 30 | 2 |
| Tyskland | 4 | 0 | 4 | 0 |
| Land ikke normalisert | 15 | 0 | 15 | 0 |
| **Sum** | **169** | **17** | **150** | **2** |

Diagnostiske hovedblokker (kan opptre samtidig): `NO_PRE_CUTOFF_RIKSTOTO_STARTS=118`, `NO_PRE_DB_T4_ATG_CLOCK_SOURCE=116`, `NO_RECONSTRUCTED_ACTIVE_FIELD=121`, `INCOMPLETE_FUNDAMENTAL_ASOF_FIELD=24`, `ATG_FULL_FIELD_GATE_NOT_PASSED=23`. Beste konkrete videre arbeid: original tidsriktig startliste, stabilt fullfelt og mapping av 15 UNKNOWN-country før noen modelltrening.

**P1 forhåndslåst kohort [PR #95](https://github.com/Maremoo2/Betting/pull/95)** – separate kilde-/protokoll-/fullfeltkontrakter med SHA-256, ikke-ettervalgbare løp, test for sene odds og etterregistrerte løp, parvis log loss/Brier for marked/Champion/CORE-004. **Ikke prospektivt evaluert** og ingen original GitHub-ekstern registreringsattest: alle aggregater merkes eksplisitt `EXPLORATORY_CLAIMS_ONLY_UNATTESTED` og `p1_validated=false`. Nye 30+ dager og reell tidsriktig originalkilde er fortsatt harde porter.

### Neste aksepterte utviklingsmål
- [ ] Review/merge #91/#92/#93/#94/#95 med **separat eksakt HEAD-bundet HQ-godkjenning**; ikke agent-merge.
- [ ] Øk andel tidsriktige originalkilder på hele løpsdager og bevis uforanderlig `source_published_at`, original startliste og scratchrevisjoner; 0 PIT-attestasjoner i faktisk 169-referansers arkiv.
- [ ] P0 original resultatkode `place=0`/`kmTime=0,0` for Skive #8 må tolkes av offisiell kontrakt før selv et **papir**-tap kan bokføres.
- [ ] CORE-004 market-free kildefaktorgrunnlag og forhåndsregistrering, deretter **nye** kronologiske OOS-dager. Fremtidig ytelse/profit kan ikke konstrueres fra fortid.

## MVP-021 FINAL – closure snapshot 4 November 2026

Historical snapshots above are preserved. This chapter supersedes their current-status claims,
not their historical evidence. Review base: `3955320482306b1d2fb475c6826502d15b3c03de`.
No merge, production write, model promotion, settlement write or new scheduled job was performed.

### Completed engineering and original-byte acceptance

- PR #143 is operationally verified. First ordinary V1 audit **41902815512**, code
  `0615b44e52593b61bcc621791673a94be7265a4b`, restored state run **41902185800**,
  artifact **13359900337**. Actual ZIP SHA256
  `e1a6ebad97780700abfc09abb34491f6c371169b476aa588bc0ac6206eaf9cb7`;
  actual SQLite SHA256 `01e0432d06c04667723f528510944b16d54e1badf103cf51c07e7db0c96e5471`,
  **701018112 bytes**. Audit **41902850675** on current base restored the same exact bytes.
  Receipt existence alone was not accepted as evidence.
- PR #145 is operationally verified for successful download and transport failure.
  First new-main CORE **41902850826** produced **89 physical / 39 full fields /
  30 model pairs / 29 WIN triples / 0 PIT**. Ordinary CORE **41906175529** then
  failed one original download and emitted only `source-unavailable.json`, unknown
  counts and `prior_verified_scorecard_invalidated=false`. A successful workflow
  with that diagnostic is a correctly blocked benchmark, not successful scoring.
- **PR #146** repairs a real audit defect: all five historical decisions have their exact
  original provider-market cohort in that restored SQLite. Earlier audit used later
  provenance prices. Exact-state local replay changes **361 checked / 554 skipped /
  5 mismatches** to **361 / 554 / 0**, retaining all five provenance differences.
  Negative read-overlay replay with one original cohort unavailable remains FAIL.
  No historical decision, source or provenance row is rewritten; no model changes.
- **PR #147** closes the remaining DEV011 integrity hole: a successful download command
  cannot validate absent, truncated or changed declared original members. Existing
  producer source blocks, true empty cohorts and genuine legacy unindexed originals
  remain distinct. Incomplete legacy archives can therefore block a new benchmark;
  preserve the prior original reference instead of reducing its denominator.
- **PR #148** repairs the demonstrated prospective capture gap. Jägersro R5 receipt
  **13356060955** arrived at **19:20:32.413975Z**, requiring **267.586025 s** to reach
  T4-minus-60; the old maximum was 240 s. Next plan **13355553911** was at
  **19:28:12.538879Z**, after **19:26Z** cutoff. Bounded waiting becomes 360 s,
  retaining clock rechecks and zero calls after cutoff. No schedule is changed and
  GitHub scheduling is still best effort. This does not certify that past race.

Separate draft PR code heads: #146 `0151242aa138c25ac51312c1fab729939d631a6f`,
#147 `bc725a58c1ed0280bfe73cfaff56593eb0df01f8`,
#148 `208c07fb9e36b43ab4f212e169797c09ef78b0a8`.
Exact-head CI runs **41908317289 / 41908322445 / 41908325713** passed, including
Ruff, full pytest and existing authenticated-original replay steps. This roadmap
addition is a subsequent documentation commit on #146; check its final HEAD CI
separately. Windows baseline and replay candidate have identical 27 failures;
they are not new regressions and are not relabelled PASS.

### First-30 research milestone

Ordinary CORE **41907500933**, artifact **13361697131**, yields **89 / 39 / 32 /
31 / 0**. Protocol was recorded at **20:26:10.590491Z**, before this result;
first 30 IDs were frozen at **20:44:32.329393Z**, before local scoring. Sort by
original selected model-freeze timestamp then race-ID; never by outcome or score.
Thirty original model ZIPs, their cohort/member hashes and both official-result
response members for every selected race were independently checked.

| Same 30 races, 299 runners | Multiclass log loss | Multiclass Brier |
| --- | ---: | ---: |
| Champion V1.1 | 2.1290872503 | 0.8614155898 |
| CORE-004 | 2.0876948876 | 0.8480727641 |
| Normalized WIN | 1.9491062640 | 0.8235196459 |

Market has lower mean loss in this small cohort. Six meeting-days across three dates,
27 SE / 3 DK races, 21 Auto / 9 Volt; availability-selected research evidence,
not robust calibration, profit or independent generalization. WIN is retained inside
hashed original frozen models, not independently verified raw WIN HTTP bytes.
Local protocol timing is not an externally attested preregistration. **Zero PIT**.
The historical 88/38/28/27 reference remains preserved; its `9a0fee8f...` hash is
the original **index.json**, not the ZIP hash.

### Unresolved P0 and source dependencies

- Skive issue #82, selected #8: original result says place=0, kmTime="0,0".
  Eskilstuna issue #144, selected #3: place=0, kmTime="19,1". Official winners and
  dividends are verified, but effective participation/refund code semantics are not.
  Both remain **BLOCKED_CONTRACT_SEMANTICS**, no loss/refund inferred or booked.
- Exact restored state contains a third overdue ticket, Bjerke 3 November R4 #6.
  Current official result has place=3 and a verified winner dividend; existing code
  is structurally ready. It awaits ordinary authorized settlement; no local write.
- V1 ordinary audit is still **FAIL**. Local corrected replay PASS does not clear
  settlement, source provenance or future operational verification requirements.
- PIT source receipt and independent Collector origin checks are wired. TMP IDs,
  scratch/publication evidence and full frozen identity remain hard source gates.
  Next observed future candidate: Bollnäs **S1_NR_2026-11-05:1**, start **11:20Z**,
  conservative T4 **11:16Z**; source suitability still requires verification.
- Permanent external archive needs owner-approved account, EU destination, budget,
  retention/access policy and actual restore drill. No storage was deployed/uploaded.
- Existing issue #104 independent PDF gold qualification remains source-dependent.
  Issue #103's former independent-review/branch-rules demand is superseded by current
  one-owner governance; it is not silently reintroduced as a merge prerequisite.

### Acceptance and MVP-022 handover

**Research MVP:** limited existing shadow research is operationally evidenced;
unconditional closure acceptance is **REVISE** pending exact-head owner acceptance
of #146/#147/#148 and ordinary post-merge evidence. No PR acceptance grants live BET.
**Production Betting: BLOCKED** on PIT, settlement integrity, verified executable
price timing, calibration/EV, risk/security and separate owner authorization.

**MVP-022 – Predictive Edge Research** may be prepared, not trained in this sprint.
Use the frozen first30 only as exploratory development evidence. Primary hypotheses:
market predictive superiority; incremental market-free history/form/distance/driver
signal; and genuinely out-of-sample calibration. Freeze comparator/configuration
hashes, keep fundamental and market signal separate, use chronological training and
validation, then a new untouched holdout. Proposed prospective comparator window:
**5 November–4 December 2026 UTC**, all independently predeclared NO/SE trot races,
with missing/blocked races retained in coverage. Owner registration must precede
the window; otherwise choose and register a new future window, never backdate.
No claim of edge from 30 races, no tuning-and-retesting on that cohort, no change to
Champion/CORE-004/V3.3.12 or betting hardgates without a separate mandate.

| Milestone | Observable exit | Deadline / dependency |
| --- | --- | --- |
| Original-state closure and three small fixes | Original hashes, local replay and exact-head CI | Done locally 4 Nov; drafts need owner review |
| Post-merge operational acceptance | Ordinary V1 restore/replay and fail-closed CORE receipts at accepted SHA | Only after explicit owner merge approval |
| Prospective capture and holdout registration | Original source clocks, stable IDs, scratch proof; externally recorded protocol | Before applicable future cutoff/window |
| Permanent-archive decision | Owner chooses EU account, budget, retention and access | By 10 Nov target; no deployment implied |
| Final HQ handover | Limited Research acceptance or precise remaining blockers; Production remains blocked | 13 Nov 18:00 Europe/Oslo |

