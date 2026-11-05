# BETTING HQ → DEV | MVP-021 P0 closure, independent original QA

**Dated:** 5 November 2026, Oslo · **Classification:** `LIMITED_RESEARCH_ACCEPTANCE / PARTIAL_P0_CLOSURE` · **No production betting**. Exact verified `main=62577497a4ccd3d0361da53ade360a421c759393` after the owner's independent merge of PR #150 (2026-11-05 08:44:49 UTC). All checks below are original- or GitHub Actions-based. No owner merge, canonical settlement write, runtime deployment, new schedules, model tuning, PIT retrocertification, real-money bet or `bet_authority` grant is performed here.

## A. PR #150 / #151 QA and owner merge boundary

| Item | Current exact HEAD / GitHub check | Result and owner action |
| --- | --- | --- |
| [#150](https://github.com/Maremoo2/Betting/pull/150) | `9c7396d7c7a802116e4df29eb7585b2b78d3b5d7`, [CI 41992562121](https://github.com/Maremoo2/Betting/actions/runs/41992562121): **43/43 SUCCESS steps, 1647 passed, 106 skipped, Ruff PASS**, Protected Strategy PASS, V1 Research Integrity PASS | **MERGED by owner**, integrated on `main` SHA above. Changes only five documents + one research-only isolated SQLite test; **no src, runtime workflow, Champion, CORE004 or V3.3.12 files.** `DONE / CI_PASS`. |
| [#151](https://github.com/Maremoo2/Betting/pull/151) | `678645ec93f46e5ec2a08a31d8e4b61dc4657fcc`, [CI 41993528733](https://github.com/Maremoo2/Betting/actions/runs/41993528733): **43/43 SUCCESS steps, 1645 passed, 106 skipped, Ruff PASS**, Protected Strategy PASS, V1 Integrity PASS and Provider Live Smoke PASS | `OPEN / DRAFT / MERGEABLE_STATE=clean`; **READY_FOR_OWNER_MERGE** if owner explicitly promotes draft and approves. It changes only `src/hbi/nightly.py::_finish_map`, one test file and one diagnosis document. No main merge. |

**Conflict review:** #151 branches from predecessor `2238a9...` and currently diverges from main (eleven newer main commits), but GitHub reported `mergeable=true, mergeable_state=clean`. PR #150 changes only docs / different test file; #151 updates `nightly.py`, separate test and separate doc. No overlapping runtime strategy code. Merge should still be rechecked at the actual owner merge moment; prior CI is on **exact #151 HEAD**, not a fresh prospective merge commit.

**Isolated regression:** Pre-existing `_finish_map` silently overwrote duplicate result `startNumber` with whichever row appeared last; this could accept a contradictory source as a settled loss. #151 returns an empty official finish map on any duplicate (including missing-place duplicate). Existing V/P gates then keep papers pending. Tests include duplicate winner, selected runner, contradictory Dsk/Str, repeated attempts/SQLite idempotence, valid unique `place>0`, `place=0 numeric`, `Dsk`, winner `Dividends` positive/invalid. The conflicting duplicate rows are **test-generated negative fixtures, not attributed to historical official originals**. No historical ticket is updated or settled.

## B. Three settlement tickets, one separately already settled

**Audit-owned exact historical state:** [V1 audit 41985710357](https://github.com/Maremoo2/Betting/actions/runs/41985710357), audit artifact **13395494318**, source watcher run **41934671198**, `hbi-state` artifact **13372739243**. Exact independently rehashed ZIP SHA256 `4e7f5e5a6cd488303ff30dd6af5375147e97ec1f91f7fbfdb9852e046afd5385`; extracted 707,309,568-byte SQLite SHA256 `6eb19189fa5c460869fa2295f2e82768157b765d11343b483312b3d4ad2d231a`. Receipt SHA `e4377b78c6d3d33ff0ffe68a97cada5e8cdc79dd47d5e73c8b44011be027d4c8`. `RUNTIME_REPLAY_PARITY=PASS` (364 checked, 557 skipped, zero mismatch), `SETTLEMENT_INTEGRITY=FAIL` with three overdue, `PROVIDER_INTEGRITY=WARN`. Historical five different later market-provenance observations remain diagnostics, not rewritten original decisions.

| Task | Physical race, frozen original paper | Original status / settlement qualification | Current exit |
| --- | --- | --- | --- |
| [#82 Skive](https://github.com/Maremoo2/Betting/issues/82) | `RIKSTOTO:S4_NR_2026-10-14:6`, #8, stake 25 NOK, available 3.30, stored winner #5 | No primary machine-readable `completeresults` or `raceresults` original in exact HBI state, and physical Skive race is absent from available cumulative DEV009 scorecard. Attempted direct official Rikstoto endpoints **unavailable via web source and container DNS**: **no authentic HTTP 200, request/response timestamp or raw SHA** established now. Secondary startlisten.dk is NOT a settlement contract; no proof of #8 participation, scratch/refund or `place=0 kmTime="0,0"` status. | `BLOCKED_SOURCE`. Next: authorized independent GET of both raw official endpoints with UTC, HTTP, SHA; verify participants + winner dividend + exact loss/refund semantics, then only isolated dry run. |
| [#144 Eskilstuna](https://github.com/Maremoo2/Betting/issues/144) | `RIKSTOTO:S1_NR_2026-11-03:7`, #3, stake 25 NOK, available 2.64, official winner #6 | **SOURCE_VERIFIED** in [DEV009 41998002781](https://github.com/Maremoo2/Betting/actions/runs/41998002781), original artifact **13401168385**: `completeresults` HTTP 200 observed 2026-11-03 20:25:13.662261 UTC SHA `5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091`; `raceresults` HTTP 200 observed 20:25:13.671752 UTC SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d`. Unique #6 Miami Mearas is winner, `Dividends=5.33`. Selected #3 I.D.Janis de Boom is `place=0,kmTime="19,1",odds=24,prize=150000`; #1/#2 are separate `Dsk` markers. This is NOT proof of Rikstoto settlement semantics for a numeric zero-place row. Frozen `nightly.py` only auto-accepts losing `place>0` or validated `Dsk`; source-derived negative tests in #150 correctly leave #3 pending, with no invented closing price. | `SOURCE_VERIFIED / BLOCKED_CONTRACT_SEMANTICS`. Next: authentic Rikstoto API definition for numeric `place=0` (participant vs scratch/void/refund), and isolated regression after separate owner review. Do not relax frozen contract before evidence. |
| [#149 Bjerke](https://github.com/Maremoo2/Betting/issues/149) | `RIKSTOTO:BJ_NR_2026-11-03:8`, #2, stake 25 NOK, available 2.57, stored winner #4 | Available cumulative DEV009 scorecard includes physical race but `NOT_EVALUABLE:NO_VERIFIED_FROZEN_MODEL`, `original_result_receipts=[]`. Exact restored HBI DB also has **zero** official complete+raceday original payloads. Direct official GETs for both URLs unavailable now; stored outcome #4 not sufficient for runner #2 participation or dividend/refund. | `BLOCKED_SOURCE`. Next: same authentic dual-result endpoint harvest + raw SHA/HTTP/UTC and isolated fail-closed replay. |

**Bjerke race 4 #6 is not a pending fourth ticket:** it was `SETTLED` by the pre-existing nightly worker 2026-11-04 23:33:55 UTC on its stored official result; no DEV write. Its raw original source bytes were not independently retained in this exact SQLite, so no new retrospective sign-off is implied. **No canonical settlement writes in this task**. No new loss/refund/gain or closing price/CLV recorded.

## C. Real T−4 / PIT evidence, not a retroactive certificate

**Latest actually executed ordinary [CORE003 41998002781](https://github.com/Maremoo2/Betting/actions/runs/41998002781)**, exact current main:

- Source report artifact **13400529192**, `core003-pilot-report.json` SHA `f93f9119688ad9c2e77f212f41a170c982c238b22bb223690fa2ca27ee59ec0a`: `discovered_races=195` but `races_in_fixed_cohort=[]`, `tasks_available=0`, `tasks_attempted=0`, `model_invocations=0`. This is not a failed eligible race: existing `core_shadow_pilot._pilot_race_ids` uses a fixed **90 minute** forward horizon. At source observation 08:54:08 UTC the first validated **physical NO/SE next scheduled race** in the immutable isolated pilot database is `RIKSTOTO:S1_NR_2026-11-05:1` (Bollnäs, SE, 11:20 UTC /12:20 Oslo), **over two hours away**, and thus was not eligible for this 90-minute queue. Do not extend the horizon or create a new cron merely to force capture.
- First planned conservatively timed T−4 for Bollnäs race1: **11:16 UTC /12:16 Oslo** if the original start remains unchanged. Prior [provider smoke 41996851451](https://github.com/Maremoo2/Betting/actions/runs/41996851451), raw `live-smoke.json` original SHA `c0a4d92e44570e311101e5d357e90f4781f6b847b2d2d3d4e77c56d1d10d54b5`, recorded ATG **14/14 complete** on provider race `2026-11-05_12_1`, but `source_published_at_utc=null`; all registered horse identifiers in evidence are `TMP-*`. No independent Rikstoto/ATG horse crosswalk, qualifying official scratched roster snapshot, qualified same-time WIN original or source-validated model freeze. This is a **`SOURCE_WATCH / BLOCKED_IDENTITY`** candidate, never `MODEL_ELIGIBLE` based on name/program-number match.
- PIT original artifact **13402010247**, `index.json` SHA `74c8e670e16e12e635a63a9790902beebe5bf2cdd0e2ecf1ae4e1e077bc9a925`: `results=[]`, `pit_certified_count=0`.
- PIT source receipts original artifact **13400894128**, `index.json` SHA `0670238f0b57615d0ee4eb339858a83cd6eb19d63d703086c7fb319edfdaaa6e`: `plan.eligible=[]`, `records=[]`.
- PR #148's 360-second bounded wait is **MERGED / CI_PASS**, but **NOT OPERATIONALLY VERIFIED** on an eligible actual runner; no call-after-cutoff result and no forged pass. The existing scheduled 5-minute CORE003 is the only authorized route; next genuine candidate should be captured prospectively when within source horizon, if it qualifies. No new automation.

## D. DEV011 / readiness / provider – exact main post-merge originals

The latest ordinary **41998002781** on `main=62577497a4ccd3d0361da53ade360a421c759393` ran actual original source acquisition, Collector handoff, DEV011 recovery, DEV009 scorecard, PIT and MVP019 readiness (not just a green YAML wrapper). The immutable byte hashes and source join are:

| Role | Artifact | Source JSON SHA256 |
| --- | ---: | --- |
| Cumulative DEV009 scorecard | **13401168385** | `05b0b1ba22f17542b89c1be56dee939404dcb2a180379c324b0611337c40fbdd` |
| DEV011 coverage manifest | **13400764362** | `19e10cf465d6fa5ffc01017e9fc5e216671c0369c0bade9e461704f9816f177d` |
| CORE003 source report | **13400529192** | `f93f9119688ad9c2e77f212f41a170c982c238b22bb223690fa2ca27ee59ec0a` |
| Model cohort `cohort-index.json` | source HEAD in `bet-mvp-shadow-41998002781` | `f73ddaf1b91e20d3686846eb5d5ab9ea482d5fa84c57293f5b17d64e7b22e186` |
| MVP019 source readiness | **13401776186** | `7c81b0667f420eb1528166ac0850bef415c9189746b7ecca4d6cef733034c680` |

Readiness `source_join_sha256` agrees with all four actual independently rehashed source originals. DEV011 selected **339** original archived artifacts, **327 recovered**, `download-failures.tsv` **empty**, 13 blocker entries: **5** unindexed legacy-model originals, **7** missing/unverifiable prior result indexes, **1** conflicting official-result receipt for `RIKSTOTO:S2_NR_2026-11-03:8`. The inconsistent historical receipt remains explicitly blocked; do not replace it with a newer or more convenient result. Status `INCOMPLETE_ORIGINAL_COVERAGE`, not complete archive.

The valid **89 physical /39 frozen complete model fields /34 result-scored Champion–CORE004 pairs /33 same-freeze WIN triples /0 PIT** scorecard remains **`OPERATIONALLY_VERIFIED`** on this latest ordinary main. Calibration is `SPARSE_BINS_NO_CALIBRATION_CLAIM`. First-30 research cohort is retrospective across just three dates/six racedays, market lower mean loss; no economic EV or PIT edge. [MVP-022 protocol](MVP022_PREDICTIVE_EDGE_PREREG_PROTOCOL_20261105.md) is already **MERGED AS DOCUMENT / READY_FOR_OWNER_REVIEW**, not signed, activated, prospective or trained.

Provider [main smoke 41996851451](https://github.com/Maremoo2/Betting/actions/runs/41996851451) is `SUCCESS` with `verified_countries=["SE","DK","NO","FR"]` and `errors=[]`. The FR green is **different race `2026-11-05_63_3` with 14/14**. The historically failing Vincennes FR race `2026-11-05_63_1` is **still incomplete** (17 active rows /15 matched, two runner issues) in this same new smoke. An aggregate green smoke does not clear the earlier `NO_FULL_FIELD_LIVE_PASS:FR` for FR race1, nor the older 12 LeTROT HTTP 403 / Rikstoto 500+network WARN. No parser defect or source quality relaxation established here.

Permanent EU immutable original archive remains a non-deployed owner decision: [owner architecture document](MVP021_EU_IMMUTABLE_ARCHIVE_OWNER_DECISION_20261105.md) is now in main after #150; require owner-approved region, WORM/retention, IAM, API budgets, cost and restore tests before any external state.

## E. Acceptance matrix as-of this closure

| Requirement | Status | One required next action |
| --- | --- | --- |
| PR #150 original QA + first 30 + prereg/archive docs | `MERGED / CI_PASS` | Owner review of prospective MVP-022 registration; **not** training or activation |
| PR #151 duplicate official results gate | `CODE_COMPLETE / CI_PASS / READY_FOR_OWNER_MERGE` | Owner explicitly mark ready / approve merge, then verify first ordinary shadow settlement after merge |
| V1 exact-state market replay | `OPERATIONALLY_VERIFIED` for source restoration and replay | Preserve five historical market-provenance differences as diagnostics |
| Three overdue paper tickets | `SETTLEMENT_INTEGRITY=FAIL` | Get Skive+Bjerke primary raw endpoints and Eskilstuna authoritative numeric-zero-place meaning |
| Real independently certified PIT | `BLOCKED_SOURCE / PIT_NOT_CERTIFIED=0` | Capture genuine future Bollnäs/next eligible race through existing schedule, insist on independent registration/scratch/market source; no retro-T4 |
| CORE003/DEV011/source readiness | `OPERATIONALLY_VERIFIED / INCOMPLETE_ORIGINAL_COVERAGE` | Resolve seven lost historical result source indexes and one conflicting result SHA without retrofitting outcomes |
| Provider smoke | `PASS` latest aggregate, `PARTIAL` FR race1 | Verify original FR registration/fullfield or retain FR race1 `BLOCKED_SOURCE` |
| First30/MVP-022 | `RESEARCH_MILESTONE_COMPLETE / READY_FOR_OWNER_REVIEW` | Sign future-only protocol; no known historical results as holdout |
| Archive | `BLOCKED_INFRASTRUCTURE` | Owner budget, region/retention and signed deploy approval |
| Full MVP-021 acceptance | **`NOT_FULL_ACCEPTED`** | Three settlement blockers + first authentic PIT + independent source/contract closure |

**Governance:** Deadline 13 Nov 2026 18:00 Europe/Oslo. No actual betting or paper settlement write, no model/prediction/risk/odds/staking change, no new schedule, no auto-merge. `bet_authority=false`. This is a dated, source-grounded research handoff, not a signed production go-live.


## F. Newer genuine post-merge source checkpoint: 5 Nov 2026 09:04 UTC

After this source report's first QA observation, ordinary [CORE003 41999339887](https://github.com/Maremoo2/Betting/actions/runs/41999339887) completed with genuine source/DEV011/PIT steps (not a skipped job). Exact downloaded original bytes:

- DEV009 scorecard artifact **13401279417**, `index.json` SHA256 `14ac6c767b3fe9a70ec74ecaa27078e0a40238c8bf76bac732aba9fd6cba224b`: **89 physical / 39 complete models / 34 paired / 33 same-freeze WIN triples / 0 PIT** (unchanged from predecessor). `INCOMPLETE_ORIGINAL_COVERAGE`.
- DEV011 manifest artifact **13401179916**, `manifest.json` SHA256 `a2c76a2463911cad5a17b780ef00e0ea18289b2ebeea48653e60f31fdc73899e`: **341 selected**, **329 recovered**, **13** recorded original defects; `download-failures.tsv` empty.
- Source report artifact **13401383936**, original SHA `e2908d63a541a40d598bfed55ff750f2742368bdc6bfcfb2666cf1ce43111efd`, capture 09:04:23–09:04:24 UTC: **195 discovered, zero in current 90-min fixed cohort, zero model invokes**; first genuine future NO/SE Bollnäs race1 start 11:20 UTC was still **136 min ahead**, so legitimately outside current selection horizon. Never mark this as a model-eligibility failure or 360-second timeout.
- Readiness artifact **13401199734** original SHA `66916b20f3179cd6e7b4f15d71cd088d000b739c1d0243d92e5f8872d05a470b` independently matches scorecard, manifest, source report and model cohort index SHA `83eda33cd0089e1dd364cb08b5a4bc18ee77ae909fb49ac9184d10059c7adbca`.
- PIT source receipts artifact **13401653248** SHA `545c761632de74347168e995d5f37af5c4c26faddee1c311dc58ed47ccd54207`: `plan.eligible=[]`, `records=[]`. PIT attestation artifact **13402490320** SHA `74c8e670e16e12e635a63a9790902beebe5bf2cdd0e2ecf1ae4e1e077bc9a925`, `pit_certified_count=0`. The 360-second window remains **NOT OPERATIONALLY_VERIFIED** because no eligible runner field triggered it.

This is the **newer** original snapshot for current cumulative benchmark and PIT count. Previously documented 419980 originals remain valid snapshots, not replacements or cumulative regressions. No source or betting gate changed.
