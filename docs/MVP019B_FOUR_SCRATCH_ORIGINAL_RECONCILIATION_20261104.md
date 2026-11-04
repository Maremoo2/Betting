# MVP-019B | SHA-pinned original reconciliation and operational source defect

**Research only.** No new historical freeze, retroactive PIT, changed score,
bet eligibility, price, selection, settlement or provider authority.

## Five affected physical races – before vs after PR #138

Source scorecard BEFORE: [ordinary CORE-003 41832416078](https://github.com/Maremoo2/Betting/actions/runs/41832416078),
artifact **13324990108**, original index SHA256
`a4a667bd596bde42b9e3dbed6d96247731067fe76f82b33ea816194fa68b5ff7`.
AFTER: [41842113458](https://github.com/Maremoo2/Betting/actions/runs/41842113458),
artifact **13328604183**, original index SHA256
`99634bb9654e71fcf1616ae145a9da6af1ce020569ec8a98a1d315c4fd0824ec`.
Both original index files were downloaded and SHA-verified. Four immutable
original model ZIPs and original official complete-results JSON were separately
downloaded and matched to their referenced SHA256, including the actual
frozen runner-scratch flags.

Every listed S2 row had first blocker `OFFICIAL_ACTIVE_FIELD_MISMATCH`,
and the same selected `LATEST_ELIGIBLE_PRE_T4_MODEL_INDEPENDENT_OF_WIN_AND_OUTCOME`
model SHA before and after. Every S2 row becomes
`EVALUABLE_RESEARCH_ONLY/TRIPLE_EVALUABLE`; no selected benchmark model
reference changed. WIN is embedded in that exact SHA-pinned frozen model,
not a newly fetched post-race odds quote. Clocks below are original UTC.

| Physical race ID (prefix RIKSTOTO:) | model source run / artifact | selected model SHA256 | original WIN observed UTC | result complete SHA256; result raceday SHA256 | before -> after |
|---|---|---|---|---|---|
| S2_NR_2026-11-02:1 | 41488067799 / 13162906690 | `ecf2318a1dca144046bf34c01039567f384ca673b30290d7ee76cc3fa61ccd22` | 2026-11-02 17:07:34.425541 | `f274f47f661e3014722a4ecdb3176bb842423e37608a38f6faa7dbffe0f4271d`; `108aad57bc897b30413607ca1d44beb420dcb48dca17610b62a6ec4612eae515` | NOT_EVALUABLE -> PAIR+TRIPLE |
| S2_NR_2026-11-02:2 | 41492573978 / 13164543152 | `bced22ffc0917e004aad89aaf0489866d1cebe7373eb4a5648b7850c16aa61fe` | 2026-11-02 17:35:43.182648 | `bfe0510d302433cc6308725b880aa259065598d1bd323687c3fcf1d91a869700`; `108aad57bc897b30413607ca1d44beb420dcb48dca17610b62a6ec4612eae515` | NOT_EVALUABLE -> PAIR+TRIPLE |
| S2_NR_2026-11-02:4 | 41499820309 / 13168417335 | `543b4b99afe8fa8230efa0ab1bd5c7ea338051e659962dfe75a1397e29c0e717` | 2026-11-02 18:09:56.860496 | `8d450b154abb85e1973bbcce2af8432444a0bef8df9a5845e5ed7483c4535afe`; `108aad57bc897b30413607ca1d44beb420dcb48dca17610b62a6ec4612eae515` | NOT_EVALUABLE -> PAIR+TRIPLE |
| S2_NR_2026-11-03:9 | 41708503913 / 13267816642 | `948000498efb619192fb88cde594f82e2befb6628bd9937e5dd5e31c4f96378d` | 2026-11-03 19:53:08.220772 | `7545e5b4d8c8c211add28f7c7ac203909872d10922a8e344fce54d54e71f84b5`; `93b4925d382b5ff0dd15cd67761ce868369422652b547969ad1d72fa1f16d123` | NOT_EVALUABLE -> PAIR+TRIPLE |

Scratch/result original cross-check (all SHA match):
- S2 2 Nov race 1: frozen #10 Grim Vendil and #11 Wing Tsun Brodde were scratched;
  official each `place=0, kmTime=Str`, winner #6.
- S2 2 Nov race 2: frozen #2 Palmer Scott scratched; same official Str; winner #5.
- S2 2 Nov race 4: frozen #9 Intercooler scratched; same official Str; winner #1.
- S2 3 Nov race 9: frozen #4 Bubble Queen scratched; same official Str; winner #5.

The unexpected **fifth** affected original is
`RIKSTOTO:S1_NR_2026-11-03:3`: previously counted as a model
pair, **never** a WIN triple. Its unchanged selected model
`9746b64fae5ed11f50f2327fb8812608519faf5024115f41b6bb10fa07a3c24d`
(run **41624717902**, model artifact **13224469448**) has
**#9 Queen Montana active, scratched=false**. Official original
`completeresults` contains `place=0, kmTime=Str` for #9.
Official complete SHA `4363f523e40a0a0c1a3c2a1009434093d06e171b20f80090bd56cf5858aa9cfa`;
raceday SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3a0b37e3d22bd4194b4e28e520d`,
archived from **41711979794**, observed 2026-11-03 20:25:12 UTC.
The frozen model's #9 p(win) was positive and its original WIN market
was absent; model SHA never changed. NEW verdict
`OFFICIAL_LATE_SCRATCH_NOT_FROZEN`, not an eligible score or retroactive
reshaping of a frozen model.

**Arithmetic on physical IDs:** Four formerly blocked S2 races join both
benchmarks (+4,+4); one formerly counted S1 model-only race correctly exits
(-1,0). Thus **16/14 -> 19/18**, model-only **2 -> 1**. The
67 -> 68 physical denominator also adds a separate unscored race; it
did not explain the benchmark delta. The definition remains one physical
race with latest eligible *pre-T4*, outcome-independent model freeze,
independent verified official result, and for a triple a normalized
same-freeze WIN vector. No original is rewritten. Subsequent independent
[41876750467](https://github.com/Maremoo2/Betting/actions/runs/41876750467)
artifact **13347262179**, index SHA
`2416b18f14f0c1acec80c22574656276529facc6243cb9a0b86a8e836c738a74`,
has **78/30/20/19**, 0 PIT; these extra later pairs are not reattributed
to PR #138.

## New documented original-join implementation defect

Ordinary CORE-003 [41879063497](https://github.com/Maremoo2/Betting/actions/runs/41879063497)
emitted genuine originals with compatible source SHA links:

| Original JSON and artifact | SHA256 |
| --- | --- |
| DEV009 scorecard **13349440390**, `index.json` | `6ec0392fd9620b41be90610b5348a019e0a9e43a975562960f8f04d2cbd61a9a` |
| CORE003 source **13348981022**, `core003-pilot-report.json` | `ab5a773ef530b061659d2ff2ee78f16806fd97637be6c57f29768d9c51cad560` |
| Model cohort **13348981011**, `cohort-index.json` | `f3af0f08f203044b0cede78ca41b395828144aad794ec21ace3ef4520541dec7` |
| DEV011 coverage **13349320545**, `manifest.json` | `a9b5c7efa0a35191f4693658df58161d553556f3dcc4e1ecc638a2c8b0c4a01e` |

Source index references the exact source-report SHA; manifest and scorecard
share inventory SHA; no archived source errors. **79** cumulative physical
race IDs, **31** complete model fields, **20** scored pairs, **19** WIN
triples; **7** current source-cohort race IDs, of which 6 overlap cumulative.
`RIKSTOTO:S3_NR_2026-11-04:4` is **source-only** because the current
model archive has not yet been published to cumulative inventory. Source
membership must not demand that this race already exist in the prior
scorecard. Cumulative benchmark stays **79**, source cohort **7**, unique
union **80**, *not* 80 result-scored races.

The fix changes **only** MVP-019 readiness, leaving MVP-016's historical
originally-joined benchmark unchanged. It validates each of four genuine
source originals, current membership, model/source SHA, archived scorecard
denominator, negative source-tampering tests and disjoint source-only rows.
No synthetic model/outcome, scorecard writes, new collector/provider GET,
PIT certification or BET.

## Five best source candidates from same original cohort (not prices/odds)

Observation: **2026-11-04 17:38 UTC**. All five have complete ATG
fundamentals, matched research-only name+program-number source and an actual
pre-cutoff research model processed, but **zero independent ATG–Rikstoto
registered identities, zero collector model-input approvals and zero PIT**.
Historical morning Collector source is not a fresh official scratch receipt
at T−4. A research model is **not** a qualified PIT freeze.

| Physical race ID suffix | Active history | T−4 conservative UTC | WIN source at T−4 | Frozen/collector scratches | Missing decisive original |
| --- | ---: | --- | --- | --- | --- |
| S3_NR_2026-11-04:1 | 11/11 | 17:46 | Complete | #9 Five Carat, morning | independent IDs + timed official scratch proof |
| S2_NR_2026-11-04:3 | 11/11 | 17:59 | Complete | #8 Lion Journey, morning | independent IDs + timed official scratch proof |
| S3_NR_2026-11-04:2 | 11/11 | 18:11 | Not complete | none morning | independent IDs + full WIN time-consistent original + scratch proof |
| S3_NR_2026-11-04:3 | 8/8 | 18:35 | Not complete | none morning | independent IDs + full WIN time-consistent original + scratch proof |
| S2_NR_2026-11-04:5 | 9/9 | 18:47 | Not complete | none morning | independent IDs + full WIN time-consistent original + scratch proof |

Remaining current S3 race 4 is source-only relative to cumulative, 10/10
ATG history, no verified WIN, independent ID or official T−4 scratch receipt.
S2 race 4 has explicit active-set, retained/live roster and SQLite field
conflicts, and incomplete ATG cohort; must not be admitted by matching names
or stripping the blockers. ALL require a fresh authorized original before
T−4. The above cutoff times are **historical source timestamps**, not
assertions that the cutoffs are still in the future.

## P0 integrity and archive blockers

Newest source-verified main audit:
[41879477950](https://github.com/Maremoo2/Betting/actions/runs/41879477950),
artifact **13347244894**, `research-v1/v1-system-audit.json`
SHA256 `54f01128607fc59b27a5fb7723d9ef3f165cfe01308af40af1a7b18672cb3fb6`.
Audited historical state matches the main watcher state [41878788182](https://github.com/Maremoo2/Betting/actions/runs/41878788182),
artifact **13348416076**, original extracted SQLite SHA256
`10d77c71c6f07910ed94aa3bfc3a9c642404b1451c227408fc7207f84c624f57`
(905 shadow runs and 15195 provider fetches match audit);
the V1 workflow itself prints only `STATE_RESTORE=RESTORED` and
does not independently pin the chosen artifact ID. Thus source
correspondence is verified via record counts, not an audit-owned DB SHA
attestation.

Five exact frozen replay mismatch race IDs unchanged:
`S2_NR_2026-10-09:5`, `MO_NR_2026-10-17:10`,
`S4_NR_2026-10-21:9`, `S2_NR_2026-10-22:5`,
`S3_NR_2026-10-25:11`, all
`combined_probability_mismatch` + `conflict_score_mismatch`.
All five `decision_provenance.recorded_at_utc` are **later** than original
decision creation, so independent old-time provenance must be found before
any decision replay is marked PASS. Preserve historical decisions.

Settlement latest **FAIL 2**, not 1:
- Skive 14 October, `S4_NR_2026-10-14:6`, ticket
  `a55a504a-bc34-487d-aced-75326dcb2b59`, paper selection #8, 25 NOK,
  stored outcome #5, no official complete+dividend source; issue #82.
- Eskilstuna 3 November, `S1_NR_2026-11-03:7`, ticket
  `f2b7e174-c650-4709-8cbb-924c30413ab9`, paper selection #3, 25 NOK,
  stored outcome #6; same official source/settlement requirements, no
  booking entry or paper P/L write.

Provider integrity **WARN**: 14 recorded source failures, **12**
LeTROT HTTP 403, **1** Rikstoto HTTP 500, **1** Rikstoto unreachable;
do not infer that unsuccessful GETs provided verified horse inputs.

Jägersro `RIKSTOTO:S3_NR_2026-11-04:5`: planned T−4
**20:26 Europe/Oslo** if original start unchanged. No prospective
PIT proof as of this audit, no post-start reconstruction. The preexisting
owner-controlled aftercheck remains authoritative; do not duplicate it.

Permanent external original archive is **BLOCKED_INFRASTRUCTURE**;
#135 provides only private local append-only tooling, not a deployed WORM
retention and access-control service. All findings `bet_authority=false`.
