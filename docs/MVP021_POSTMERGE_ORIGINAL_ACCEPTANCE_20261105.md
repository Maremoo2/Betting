# MVP-021 | Post-merge original-QA and limited research acceptance

**Kontrolltidspunkt:** 5. november 2026 ca. 08:30–09:00 Europe/Oslo · **Repository:** `Maremoo2/Betting` · `main=2238a9b891b16cd74ced7eaa581c630dd572f4b9` · **Frist:** 13.11.2026 18:00 Oslo. **Ingen autorisert live betting**.

**Akseptgrense:** Denne rapporten er `MVP-021 PARTIAL/LIMITED RESEARCH`. `FULL ACCEPTED` krever faktisk oppgjørskilde, første ekte PIT-sertifikat og øvrige P0-gater. Aldri anta at workflow `SUCCESS` betyr kilde-/modell-/resultat-`PASS`.

## P0-A – Merget kode vs ordinær operasjon

- Owner merge [PR #143](https://github.com/Maremoo2/Betting/pull/143) til main, 2026-11-04 20:02:54Z, merge `0615b44e52593b61bcc621791673a94be7265a4b`: V1 exact-state restore-kvittering.
- [PR #145](https://github.com/Maremoo2/Betting/pull/145), merge 20:03:07Z, commit `3955320482306b1d2fb475c6826502d15b3c03de`: DEV011 failed-download hardgate.
- [#146](https://github.com/Maremoo2/Betting/pull/146), 5 Nov 07:13:05Z, `cc7f6d15c08a255a0aa3c01587a69340cc77cdbd`; [#147](https://github.com/Maremoo2/Betting/pull/147), 07:13:15Z, `b36a2bac1bf807b38357b7fc6f1f0e5de2566aac`; [#148](https://github.com/Maremoo2/Betting/pull/148), 07:13:26Z, `2238a9b891b16cd74ced7eaa581c630dd572f4b9` (bounded PIT wait 240→360 s).
- [Main CI 41985709967](https://github.com/Maremoo2/Betting/actions/runs/41985709967) `CI_PASS`, 1 639 passed /106 skipped. Main Research Integrity `PASS`; V1 Audit `FAIL`; Provider Live Smoke `FAIL`.
- Latest [CORE-003 41987283702](https://github.com/Maremoo2/Betting/actions/runs/41987283702) and [41986285369](https://github.com/Maremoo2/Betting/actions/runs/41986285369) show `workflow SUCCESS`, **but actual source capture, Collector import, DEV011 recovery, scorecard, PIT and MVP019 readiness STEPS SKIPPED** due to existing execution gate. Both have **zero** published artifacts. **Not** `OPERATIONALLY_VERIFIED` for PR #146–#148.
- Last *genuine, executable and completed* CORE-003 with scorecard: [41911371831](https://github.com/Maremoo2/Betting/actions/runs/41911371831), 4 Nov, predecessor main SHA `3955320482306b1d2fb475c6826502d15b3c03de`. DEV009 original artifact **13364215238**, `index.json` SHA **`6dd2ab97bc4e2893e22836777290e9f3d985e0a88c99d5b7df57a68fa6cfa019`**, original DEV011 manifest artifact **13363715590**, `manifest.json` SHA **`e9395a7c4f95062b3752cc1d444f99ab3d8007c4c2250794e2c11ca9e5e94217`**; Source Readiness artifact **13362413534**, `index.json` SHA **`cccbcb4909ccf8d8b2cb1bafa91fba70f74909bd4b276ba62662b728ded52ed9`**; PIT artifact **13362753002**, `index.json` SHA `74c8e670e16e12e635a63a9790902beebe5bf2cdd0e2ecf1ae4e1e077bc9a925` (`results=[]`).
- Genuine scorecard counted **89 distinct physical/39 complete models/34 result-scored pairs/33 same-freeze WIN triples/0 PIT**, `SPARSE_BINS_NO_CALIBRATION_CLAIM`. DEV011 **4 509 artifacts /46 original pages /316 recovered**, with **five unindexed legacy models, six unavailable prior result indexes and one `RIKSTOTO:S2_NR_2026-11-03:8` conflicting official result original**; cumulative status **`INCOMPLETE_ORIGINAL_COVERAGE`**, not a completeness pass. Readiness links the exact four source SHAs, but current model cohort `0`, source races `0`, no new freezes in that run. Later gate-skipped runs cannot replace it.
- The separate *first 30* research milestone is locked chronologically in [source manifest](MVP022_FIRST30_EXPLORATORY_SOURCE_LOCK_20261105.json) with original scorecard SHA. Original complete- and raceday-bytes for all 30 were independently re-hashed (60 SHA matches), without rewriting any scores. Data are **exploratory/not PIT**; 33 is latest observed research coverage, not 33 independent PIT.

## P0-A2 – First **actually executed** post-merge ordinary run (new observation 09:02–09:08 Oslo)

[CORE-003 41991423533](https://github.com/Maremoo2/Betting/actions/runs/41991423533) on exact main `2238a9b891b16cd74ced7eaa581c630dd572f4b9` finished `SUCCESS` **with actual source capture, immutable DEV011 GETs, DEV009 scorecard and MVP019 readiness steps executed**. The earlier 41986285369/41987283702 remained gate-skipped; this run supersedes their operational limitation *for component execution, not for PIT success*.

All original ZIP members downloaded and independently SHA256 rehashed; the readiness source-join verifies exactly these four source SHA values:

| Source original | GitHub artifact ID | Original JSON SHA256 |
| --- | ---: | --- |
| Cumulative DEV009 index | **13397674684** | `ec47b3f8a0e9d2c679d0024fa2ff0e095ccf8b1f9e19fbe701082f053ff3a873` |
| DEV011 manifest | **13398273350** | `4a89421c843c04ae688dd5d88ea96812f1bb090d59fbb8669df3392d8eb3a710` |
| CORE003 original report | **13398866360** | `98d7da115e17fdb1077213227e8d1afd415423cf5e296f3990e57bdee9b00626` |
| Frozen model cohort index | **13397619842** | `20a5c4dff62857ed58219ab44105f3618cbb88ce7625b4bdc0319bc9f73d90c8` |
| Joined source-readiness index | **13397674668** | `04a8fee51ffc5fb3c8222645e54fa322cc7011936b2475fe2e012b2222949d9a` |
| PIT attestations | **13397674679** | `74c8e670e16e12e635a63a9790902beebe5bf2cdd0e2ecf1ae4e1e077bc9a925` |
| PIT capture receipts | **13398073771** | `47b5ca4d01588477b3beb9fc1f6ee73ad40b2e7f2b0fcc367d4aff379a07745c` |
| Collector handoff | **13397594966** | `70866bd5971dd6c69bac526ca7b90d1c1b31c90a868af07a68e8949847c32743` |

DEV011 `download-failures.tsv` in artifact 13398273350 is **exactly empty** with SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. Source journal `started_at=2026-11-05T08:02:19Z`, `finished_at=08:02:21Z`, `discovered_races=195`, yet `races_in_fixed_cohort=[]`, `tasks_available=0`, `tasks_attempted=0`, `model_invocations=0`. Collector handoff `records=[]`; model cohort `processed=[]`; PIT capture `records=[]`, attestation `results=[]`, `pit_certified_count=0`. Thus **actual research source/DEV011/readiness pipeline is `OPERATIONALLY_VERIFIED`** on merged main, but **future qualified PIT eligibility is still `BLOCKED_SOURCE`** and 360-second capture wait has not been exercised for a real eligible runner field.

DEV009 benchmark remains **89 distinct /39 full frozen fields /34 official model pairs /33 same-freeze WIN triples /0 PIT**. `calibration.status=SPARSE_BINS_NO_CALIBRATION_CLAIM`. DEV011 manifest selected **329** historical artifacts, **318** recovered with source SHA; **12** missing/blocked: five historical `UNINDEXED_LEGACY_MODEL_ORIGINAL`, six `MISSING_OR_UNVERIFIABLE_ORIGINAL` source-unavailable result indexes (not actual downloads failed in THIS run), and one `CONFLICTING_OFFICIAL_RESULT_RECEIPTS` for `RIKSTOTO:S2_NR_2026-11-03:8`. Correct status `INCOMPLETE_ORIGINAL_COVERAGE`; old data not invented. `source_only_not_yet_cumulative=[]` for this **empty** current cohort; distinct-source-horizon regression was verified in older active cohort, not falsely inferred from an empty cohort.

## P0-B – Exact-state V1, independent ZIP and SQLite verification

[Ordinary audit run 41985710357](https://github.com/Maremoo2/Betting/actions/runs/41985710357) on **exact** main SHA above, original audit artifact **13395494318**:
- `v1-state-restore-receipt.json` SHA `e4377b78c6d3d33ff0ffe68a97cada5e8cdc79dd47d5e73c8b44011be027d4c8`; selected watcher source run **41934671198**, artifact **13372739243**, ZIP SHA **`4e7f5e5a6cd488303ff30dd6af5375147e97ec1f91f7fbfdb9852e046afd5385`**, restored SQLite SHA **`6eb19189fa5c460869fa2295f2e82768157b765d11343b483312b3d4ad2d231a`** (**707 309 568 bytes**), restore time `2026-11-05T07:14:35.606226+00:00`, audit run **41985710357** and audit SHA `2238a9b891b16cd74ced7eaa581c630dd572f4b9`. Both ZIP bytes (206 013 908) and extracted SQLite bytes were independently re-hashed exact.
- `research-v1/v1-system-audit.json` SHA `ef34e9077c6058ac2057eb02da6817f9fb7d65484e9423ba933b8bc9522a6586`: `temporal_integrity=PASS`, `runtime_replay_parity=PASS` (**364 checked,557 skipped, 0 mismatches**); five older cases now preserved as explicit `PROVENANCE_PRICES_DIFFER_FROM_FROZEN_SOURCE` diagnostics. Parity uses original frozen source-market basis, **never later odds**. `provider_integrity=WARN`, 14 historical GET failures (12 LeTROT 403, Rikstoto 500 and network unreachable); `settlement_integrity=FAIL` with **three overdue tickets**; therefore `v1_engineering_complete=false`.
- A prior audit [41942615854](https://github.com/Maremoo2/Betting/actions/runs/41942615854) on the **same** source SQLite SHA and older code SHA `3955320482306b1d2fb475c6826502d15b3c03de` still reported five runtime mismatches. The old/new difference is therefore `audit_code_revision`, not a demonstrated change to original model or source DB. Exact-state chain now **OPERATIONALLY_VERIFIED**, V1 **OVERALL FAIL** (settlement).

## P0-C – Settlement issues and exact historical correction

From the **same immutable V1 SQLite** via read-only SQLite:
- [#82 Skive](https://github.com/Maremoo2/Betting/issues/82), `RIKSTOTO:S4_NR_2026-10-14:6`: `a55a504a-bc34-487d-aced-75326dcb2b59`, paper WIN #8 /25 NOK / available odds 3.30 / decision `2026-10-14T16:37:12.231261Z`, stored winner #5. Ticket `SHADOW_BET`; **no official complete+raceday original nor verified selected participation/dividend** stored in this exact SQLite; direct public Rikstoto GET unavailable. `BLOCKED_SOURCE`.
- [#144 Eskilstuna](https://github.com/Maremoo2/Betting/issues/144), `RIKSTOTO:S1_NR_2026-11-03:7`: `f2b7e174-c650-4709-8cbb-924c30413ab9`, paper WIN #3 /25 NOK /2.64, decision `2026-11-03T13:25:24.696763Z`, stored winner #6. Official `completeresults` raw SHA `5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091`; `raceresults` SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d`; #6 `Dividends=5.33`, selected #3 `place=0/kmTime="19,1"/odds=24`. ATG's official general abbreviations say `O=unplaced`, `s=scratched`, `d=disqualified`, but **this does not prove Rikstoto JSON's `place=0 + 19,1` contract**. The frozen `nightly.py` settlement contract admits finish>0 or unique `Dsk` with positive participation odds, **not** selected #3 numeric `kmTime` at place zero. `BLOCKED_CONTRACT_SEMANTICS`, ticket `SHADOW_BET`, no P/L/CLV.
- **Correction to HQ prompt:** Bjerke `RIKSTOTO:BJ_NR_2026-11-03:4` selected #6, ticket `72518502-350a-457e-adce-20ce32b8d163`, **already SETTLED by existing nightly**, `2026-11-04T23:33:55.240144Z`, recorded finish 3, paper gross 0/net −25, null close/CLV and result source URL from Rikstoto. DEV did not run settlement or modify this state. **Raw official complete+raceday bytes are not stored within the exact V1 database**, so independent source-byte re-verification of *this pre-existing settlement* remains `PARTIAL`, not a retroactive new authorization.
- The **third actual V1 audit failure** is [#149 Bjerke race 8](https://github.com/Maremoo2/Betting/issues/149), `RIKSTOTO:BJ_NR_2026-11-03:8`, ticket `0a3d1cdf-b1bc-43c3-aee1-b520a231067a`, paper WIN #2/25 NOK/2.57, decision `2026-11-03T20:23:55.843777Z`, stored winner #4. `SHADOW_BET` and original post-race complete+raceday files **absent** from exact historical archive. `BLOCKED_SOURCE`; do not infer loss/refund from stored winner.
- Existing [`test_official_settlement.py`](../tests/test_official_settlement.py) already tests Dsk/Str/place=0, idempotence, incomplete results and dividend. Additional isolated [source-derived regression tests](../tests/test_mvp021_exact_original_settlement_boundaries.py) cover **actual original Eskilstuna numeric zero-place, official Dsk and dividend values**, invalid dividend, contradictory winner, and source missing. Tests mutate **only temporary test SQLite**, never canonical state. No actual settlement writer, thresholds or source semantics changed.

## P0-D – PIT and next true future candidate

Existing #148 source `src/hbi/core_t4_receipt.py` now has `MAX_WAIT_SECONDS=360` and checks `clock>=T4` *before each of the three official GETs*, rejects completed at/after cutoff and requires Collector/PIT source-attested field and original timings. This is **MERGED / CI_PASS**, but the newest post-merge CORE-003 runs 41986285369 and 41987283702 **skipped the capture stage**, so it is **NOT YET OPERATIONALLY VERIFIED** under actual source pressure. Latest genuine original PIT `13362753002` has `pit_certified_count=0`, no false certificate.

Potential real next NO/SE source candidates from [provider live smoke 41985710135](https://github.com/Maremoo2/Betting/actions/runs/41985710135) at 07:15Z:
- Sweden provider `2026-11-05_12_1` (14/14 active histories, `race_start_utc=2026-11-05T11:20Z`); selected as first **SOURCE_WATCH**, *not* approved physical race ID, no independent registered cross-provider `TMP-*` identities, official final scratch/Collector provenance or complete WIN PIT bundle.
- NO Biri provider `2026-11-06_96_1` (12/12 schema, source-research only) as next-day fallback, same independent identity/scratch blocks.
- Actual future race is not `MODEL_ELIGIBLE` until all strict original hardgates pass; no retro-PIT, extra schedule or bet.

## P0-E – Provider smoke

Original [smoke 41985710135](https://github.com/Maremoo2/Betting/actions/runs/41985710135), artifact **13395883047**, `live-smoke.json` SHA256 `9b4f88378317ce2ea221882af45f08a58f6e824df065a2c39a27332d5c4c833c`, status **FAIL `NO_FULL_FIELD_LIVE_PASS:FR`**. FR Vincennes provider race `2026-11-05_63_1`: active field **18**, only 17 rows parsed, #16 Zoom Diamant `INVALID_LIFETIME_COUNTS`, #18 Junkie (Swe) `IDENTITY_NOT_UNIQUE_OR_MISMATCH`; some other FR races have `PROVIDER_RACE_IDENTITY_OR_TIME` or `LETROT_FULL_FIELD_CORROBORATION_FAILED`. Same run's `provider-research.json` SHA `1d4e661403934818fe2200f1c0d310ab55503901c9b1aaf974cdb7a109532049` records several French LeTROT HTML GET 200, but **PUBLIC_HTML_ONLY_NOT_A_VERIFIED_HISTORY_CONTRACT**. This does not clear 12 older historical 403 or prove a registered cross-ID. `BLOCKED_SOURCE` vs `PROVEN_CODE_BUG`: no actionable code defect shown; no gate relaxation or PASS-forcing.

## P1 – Archive and Manual QA

[Owner-ready immutable EU archive decision](MVP021_EU_IMMUTABLE_ARCHIVE_OWNER_DECISION_20261105.md): original SHA receipts, object WORM/versioning, IAM segregation, recoverability, source API budgets and realistic unverified cost scenarios; no deploy. Status `BLOCKED_INFRASTRUCTURE`.

**MANUAL-QA-001 – 04.11.2026:** HQ-supplied facts (not independently rechecked against 6 original betting slips): 6 manually submitted V5/V4X/DDX tickets, **632 NOK stake, 0 payout, −632 NOK**. This is manual decision-discipline deviation **NOT** proof of Champion/CORE-004 model error or a source-based positive EV. Guidance only: any coupon without whole-field independent p(win), price-aware margin, original positive EV and approval must be labelled `ENTERTAINMENT / NON_MODEL_APPROVED`; show maximum loss and do not label it `BET` under V3.3.12. No retrospective regrading of tickets, model, stakes or decisions.

## Akseptmatrise og frist

| Task | Status at 5 Nov | Exact next action |
| --- | --- | --- |
| Post-merge source-joined CORE-003, #146–#148 | `PARTIAL` (gate-skipped) | First actually executed ordinary NO/SE capture after 09:00 Oslo; check all original roles and SHA. |
| Exact-state V1 restore and 364 replay | `OPERATIONALLY_VERIFIED` | Continue comparing next genuine V1 restore with source SHA; leave past provenance diffs diagnostic. |
| Full V1 engineering | `FAIL` | Resolve all three overdue tickets with true official source and separate owner settlement approval. |
| Skive #82 | `BLOCKED_SOURCE` | Capture authentic complete+raceday original and participation/Dividends. |
| Eskilstuna #144 | `BLOCKED_CONTRACT_SEMANTICS` | Verify *Rikstoto JSON* numeric place-zero semantics, not just ATG summary. |
| Bjerke race4 #6 | `SETTLED_IN_HISTORICAL_STATE / PARTIAL_RAW_AUDIT` | Source-rehash original if accessible; no duplicate settlement. |
| Bjerke race8 #149 | `BLOCKED_SOURCE` | Obtain complete+raceday original then read-only isolated contract replay. |
| PIT 360s and independent IDs | `IMPLEMENTED / CI_PASS / OPERATIONAL_NOT_VERIFIED` | Real future source capture, strict pre-T−4 source originals. |
| 30 first original triples | `RESEARCH_COHORT_LOCKED / NO_PIT` | No retuning; owner review prospective protocol. |
| MVP-022 preregistration | `READY_FOR_OWNER_REVIEW / NOT_ACTIVE` | Owner must sign future period and exact SHA before first selected race. |
| Permanent archive | `BLOCKED_INFRASTRUCTURE` | Owner chooses EU region, retention, access & budget; no deployment. |
| Production betting | `BLOCKED` | Requires separate explicitly authorized production acceptance. |

**Realistic by 13 Nov 18:00:** exact-state replay and first30 lock already verified; new original source-driven settlement, all-France fullfield and first PIT cannot be promised without provider/Collector originals and separate owner approval. Claim `MVP-021 LIMITED RESEARCH ACCEPTED` only for individually verified delivered items; `MVP-021 FULL ACCEPTED` currently **NOT MET**. No automatic merge, no autobet, `bet_authority=false`.
