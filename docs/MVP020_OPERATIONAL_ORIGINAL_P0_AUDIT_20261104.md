# MVP-020 | Operational originals and V1 exact-state recovery (4 Nov 2026)

**Safety:** Research-only, no betting/settlement/state write, no PIT admission, no model refit, no changed Champion/CORE-004/V3.3.12/odds/stakes/decisions, no automation. All external official GETs must be timestamped; observed after T−4 must never be represented as pre-T−4.

## A. First ordinary CORE-003 after owner-merged #142

Main `4fe98264522e8453589a83bda6d9e59c53b22147` is the exact owner merge commit of PR #142; parents `640908bfc7f3aa01c80ddb8daca81d0846835068` and `7ee12616e7950319870cee490f6a63631f0178a6`. [CORE-003 run 41892222531](https://github.com/Maremoo2/Betting/actions/runs/41892222531) is the first full **successful** run on this SHA. Independent download-and-hash of the actual JSON contents:

| Artifact role | Artifact ID | Content SHA256 |
| --- | --- | --- |
| MVP-019 readiness index.json | 13353059281 | `3424873d6b2a5b26dd25f59885a0a4cc63cf1e4d7621e041f14cb945919c4188` |
| DEV009 cumulative scorecard index.json | 13353313617 | `be179e26eddab8ac41ec21b79f0acd9acfba106e8fe0177c0d06a628b68cb9a1` |
| CORE003 source core003-pilot-report.json | 13354847436 | `809af8ac8919d49f6b564d502effb010f47c62d7ca67019eed63224bc5e22453` |
| Model cohort cohort-index.json | 13354606909 | `0471d143c369276cd7230610343039fd85ab417cdf1e86db0e83e3162a3afa8a` |
| DEV011 original coverage manifest.json | 13352954946 | `24b917f1d436b89991b949ae605dc77795598d5931150ffba522cf6712788f54` |

The readiness index's four source SHA anchors exactly match the independently hashed JSON originals. The source cohort index references the same source-report SHA. This is **OPERATIONALLY_VERIFIED**, unlike a CI replay.

Cumulative **86 physical, 36 complete original model full fields, 26 result-scored Champion/CORE-004 pairs, 25 same-frozen WIN triples, 0 PIT**, status `INCOMPLETE_ORIGINAL_COVERAGE`. Current source **7** physical IDs; **5** were research-model processed, **0** strict Collector model inputs approved, **0** independently PIT-certified. Current source statuses: **5 BLOCKED_IDENTITY, 2 BLOCKED_ATG_FULL_FIELD**. `RIKSTOTO:S2_NR_2026-11-04:9` is in source cohort but not yet in cumulative scorecard. It has **12/12 ATG** but lacks complete WIN and official stable cross-provider IDs; **do not** count as result-scored or backfill it to 87. Source-only union 87 is **not** the benchmark denominator. Genuine 41879063497 source-only prior race `RIKSTOTO:S3_NR_2026-11-04:4` was independently replayed in PR #142 authentic CI (run 41882707879), including nine negative source-tamper cases. The first new ordinary run independently exercises the same valid distinct-horizon behavior.

Current source pipeline stages: DISCOVERED 7, SOURCE_CAPTURED 7 (collector original startlist SHA reported), VALIDATED **0** strict independent full-field ID/scratch crosswalk, MODEL_ELIGIBLE **0** strict, research-only models 5 (NOT strict freezes), PIT/FROZEN **0**, RESULT_VERIFIED **0** for current prestart-only cohort, WIN_EVALUABLE **0** new current races; cumulative verified WIN triples **25**. Never equate research `MODEL_READY` to a qualifying PIT freeze.

## B. Jägersro, physical S3 race 5

Original morning Collector receipts contained in the model cohort from 41892222531: 9/9 active, no morning scratches, all 9 Rikstoto registration IDs are `TMP-S3-20261104-05-*`, ATG 9/9 at 18:02:40 UTC, research model computed 18:58:37 UTC, WIN not complete at source cutoff 18:58:34 UTC. Start 19:30 UTC (20:30 Oslo), conservative T−4 19:26 UTC (20:26 Oslo); morning /starts observed 06:21:01 UTC SHA `fe1cde9c8642d8f526eb95c69c524c7b24243ba6669540f9126197e5ff4ea386`, morning PDF observed 06:21:03 UTC SHA `ddbe3bf9fe96dd04492509c184de9ae6491e9660f4f2772d2b8f07645eb74ba2`. Cross-provider independent registration and official post-morning scratch/T−4 receipt remain unverified. `PIT_NOT_CERTIFIED / BLOCKED_SOURCE`. No retrospective race result, later WIN, or PIT inference. Existing owner-scheduled aftercheck only; no duplicate automation.

## C. Settlement – two separate paper-only tickets

Read-only restored candidate watcher original: [run 41890574018](https://github.com/Maremoo2/Betting/actions/runs/41890574018), `hbi-state` artifact **13352639685**, ZIP created 18:48:08 UTC, extracted `data/hbi.sqlite` SHA256 `aacf2d95117e1f6eee24fa19ec3df20e220fa84d4e712e3e025dd670e770e7db`. Both tickets remain `SHADOW_BET`, original `gross_return_nok`, `net_pnl_nok`, `closing_price`, `clv`, `settlement_source_uri` are NULL. Audit grace **24h** after race start.

**Skive 14 Oct / issue #82:** `RIKSTOTO:S4_NR_2026-10-14:6`, ticket `a55a504a-bc34-487d-aced-75326dcb2b59`, decision 2026-10-14 16:37:12 UTC, 25 NOK paper #8, available 3.30; stored `outcomes` winner #5 only. Candidate SQLite contains 8 `RACEDAY_STARTS` and 4 `CONTENDER_GATE_V2_1` for the raceday and **zero** immutable original `OFFICIAL_COMPLETE_RESULTS` or `OFFICIAL_RACEDAY_RESULTS` payloads. No qualifying official dividend original; no settlement. `BLOCKED_SOURCE`.

**Eskilstuna 3 Nov:** `RIKSTOTO:S1_NR_2026-11-03:7`, ticket `f2b7e174-c650-4709-8cbb-924c30413ab9`, decision 2026-11-03 13:25:24 UTC, 25 NOK paper #3, available 2.64. Stored outcome winner #6. **Separate official source evidence does exist** in the genuine [CORE-003 scorecard 41892222531](https://github.com/Maremoo2/Betting/actions/runs/41892222531), artifact **13353313617**. Complete original from run **41711979794**, observed 2026-11-03 20:25:13.662261 UTC, HTTP 200, source `https://www.rikstoto.no/api/results/raceDays/S1_NR_2026-11-03/7/completeresults`, raw SHA `5f2e15d0167c10124cfd4d5099e96698e17df832a7a6dc65b837e8c32680a091`; raceday original observed 20:25:13.671752 UTC, HTTP 200, source `https://www.rikstoto.no/api/results/racedays/S1_NR_2026-11-03/raceresults`, raw SHA `1941cee46964f14a87f6b52bd54b58e40fc7e3d22bd4194b4e28e520d`. Both raw files were downloaded and independently SHA-verified. Official `isComplete=true`; unique #6 Miami Mearas wins, `finalOdds.winOdds["7"]["6"]={payoutStatus:"Dividends", odds:5.33}`. Selected #3 I.D.Janis de Boom has `place=0, kmTime="19,1", odds=24`. A numerical kmTime strongly supports a participant but **the current frozen `nightly.py` contract permits loss with `place>0` or exact `place=0, kmTime="Dsk"` with positive participation odds**, NOT a numeric kmTime at place zero. Therefore under the **frozen** contract this settlement remains pending despite genuine official original and positive dividend. Whether numeric kmTime plus odds can certify unplaced loss requires separately approved semantic contract; do not silently widen settlement allowed states or write historical P/L. `BLOCKED_CONTRACT_SEMANTICS`.

**Correct verified raceday SHA:** `1941cee46964f14a87f6b52bd54b58e40fc7e3a0b37e3d22bd4194b4e28e520d`. No settlement, refund or P/L write in this task.

## D. V1 exact-state and market-first divergence

V1 [run 41892221873](https://github.com/Maremoo2/Betting/actions/runs/41892221873), artifact **13353612873**, raw `research-v1/v1-system-audit.json` SHA256 `c3c98894efac5c7f6d630d488988aa7d4048faa804bd68437f2df41b47d648f8`, reports temporal PASS, provider WARN, runtime replay FAIL (5), settlement FAIL (2 overdue paper tickets). Original audit code printed only `STATE_RESTORE=RESTORED` (no selected artifact ID/SHA). The watcher candidate **13352639685** above is the latest observed before audit (later watcher artifact 13354177340 was created 18:58:27 UTC *after* the audit artifact at 18:58:09 UTC), and yields exactly **909 shadow_decision_runs, 15265 provider fetches, 14 failed GETs**, matching audit. This is a **strong** source-state candidate but **not a proven exact restore identity**; do not claim audit-owned SHA for historical run. MVP-020 restore receipt adds an optional SHA/id log used only by V1 audit workflow, retains original restore selection and makes future exact-state provenance verifiable.

Independent write-protected re-evaluation against the SHA-pinned candidate using original stored fundamental probabilities, provenance combination weights 1:1, and original stored normalized market probabilities yields **exact original combined probabilities and conflict scores** in all five. The **first divergence** appears only when using the different later-attached `decision_provenance.market_odds_json` normalized probabilities:

| Race ID suffix | Max abs market p difference | Max abs combined p mismatch | Original stored-market combined discrepancy |
| --- | ---: | ---: | ---: |
| S2_NR_2026-10-09:5 | 0.01985771 | 0.01141446 | 0 |
| MO_NR_2026-10-17:10 | 0.03734198 | 0.05808288 | 0 |
| S4_NR_2026-10-21:9 | 0.03411454 | 0.03187469 | 0 |
| S2_NR_2026-10-22:5 | 0.03353808 | 0.04096475 | 0 |
| S3_NR_2026-10-25:11 | 0.06779918 | 0.07895829 | 0 |

Every attached provenance row was timestamped *6–12 minutes later* than its frozen decision. Root evidence: old provenance market quote does not match saved market distribution; **not demonstrated** that model code/formula was faulty. Preserve fail as true fail, no re-frozen decision or after-the-fact quote. Further original historical market-snapshot retrieval is needed to pin the quote provenance as of decision time.

## E. Next source quality + external archive design (NOT deployed)

Prospective **as-of first source 18:58 UTC**, not an assertion of later availability: `S2_NR_2026-11-04:6` ATG9/9 WIN complete T−4 19:09 UTC; `S3_NR_2026-11-04:5` ATG9/9 WIN incomplete T−4 19:26; `S2_NR_2026-11-04:8` ATG11/11 WIN incomplete T−4 19:59; `S3_NR_2026-11-04:7` ATG11/11 WIN incomplete T−4 20:11; `S2_NR_2026-11-04:9` ATG12/12 WIN incomplete T−4 20:22. None has independent cross-provider horse registration, official timed scratch source or Collector approval; once T−4 expires it is no longer a prospective freeze candidate. S2 #7 and S3 #6 have ATG 0/12 and must remain blocked. Prioritize source-grade cross-provider registration original and full active roster before examining WIN/market; do not promote copied TMP IDs.

**Minimal permanent archive architecture proposal (NO DEPLOY):** (1) immutable source bytes in region-approved object store with object-versioning + object-lock/WORM retention policy reviewed by owner/legal, prefer at least 365 days or approved governance interval; (2) append-only SHA256 manifest with source URI, content hash, provider, race ID, HTTP status, request-start/completed UTC and provider-supplied timestamp separately; (3) encryption at rest and transit, least-privilege capture/read-only audit roles, no persistent GH runner access keys, secret-manager-issued short-lived credentials; (4) separate authoritative provider responses vs derived models, failed GETs recorded but never promoted; (5) daily audit of randomly selected byte restoration against manifest SHA and time, redundant regional copy and periodic disaster-recovery drill; (6) transparent retention expiry/legal hold and administrator dual approval; (7) explicit cost, policy, security and deployment authorization before any infrastructure write. #135 local archive is NOT an approved permanent external archive.

**Provider-integrity warnings** from pinned original candidate and V1 audit are unchanged: **12 LeTROT HTTP 403** (external access control; not evidence of validated runners), **1 Rikstoto HTTP 500** (remote server error) and **1 Rikstoto network-unreachable** (network path). No correlated parser code defect proved. Green provider live smoke checks a separate execution window and never clears historical WARN.

**Benchmark:** 25/30 same-freeze WIN triples, gap **5** at original first completed post-#142 source. This is a data volume target, NOT a profitability or betting edge metric. Champion/CORE004 must be evaluated with the same selected physical race/model-freeze original and exactly time-qualified same-freeze WIN. No refit.

**Status:** MVP-019 `OPERATIONALLY_VERIFIED`; V1 receipt implementation `IMPLEMENTED / CI_PENDING` until exact-HEAD PR checks; V1 replay `FAIL / PARTIAL_CAUSAL_DIAGNOSIS`; Skive `BLOCKED_SOURCE`; Eskilstuna `BLOCKED_CONTRACT_SEMANTICS`; PIT `BLOCKED_SOURCE`; external archive `BLOCKED_INFRASTRUCTURE`. No merge, canonical settlement, model, scoring or betting changes.
