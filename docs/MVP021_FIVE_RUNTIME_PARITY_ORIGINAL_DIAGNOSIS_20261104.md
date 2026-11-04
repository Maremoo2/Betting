# MVP-021 | Five V1 runtime parity mismatches, independent original-state candidate replay

**Scope:** Read-only forensic replay of an actual GitHub watcher SQLite artifact;
**NOT** an audit-owned exact-state attestation, no history repair, model refit,
replayed betting, synthetic timestamps or retroactive PASS.

## Immutable candidate source and audit gap

- [Watcher 41890574018](https://github.com/Maremoo2/Betting/actions/runs/41890574018), `hbi-state` artifact **13352639685**; original extracted SQLite **695,439,360 bytes**, SHA256 **`aacf2d95117e1f6eee24fa19ec3df20e220fa84d4e712e3e025dd670e770e7db`**. Independently re-extracted the exact source bytes in a read-only forensic copy.
- [V1 audit 41892221873](https://github.com/Maremoo2/Betting/actions/runs/41892221873) original report **13353612873** recorded five replay failures, two overdue paper tickets and 14 provider fetch warnings. Historical audit did **not** record restored source artifact ID, ZIP SHA or restored database SHA. Candidate watcher row/fetch counts agree with audit, **but this does not establish an exact audit-to-state source chain**.
- PR [#143](https://github.com/Maremoo2/Betting/pull/143) (not merged) adds an optional source receipt with exact source artifact ID/run/ZIP SHA/SQLite SHA, plus MVP-021 audit-specific UTC restore instant, audit run ID and actual checked-out Git SHA. Only the first future V1 audit actually running that code can validate an audit-owned exact state.

## Original persisted inputs vs later-attached provenance

Query each physical race's unique original `shadow_decision_runs` and
`decision_provenance` row in immutable SQLite. Parse persisted fundamental
`f`, original normalized `market_probabilities_json` `m₀`, saved
`combined_probabilities_json` and conflict score. The attached
`decision_provenance.market_odds_json` is a *different, later-timestamped*
decimal-odds map; normalize its inverse-odds into `m₁`.

For both inputs independently calculate
`normalize(f_i^a m_i^b)` with the **original saved** weights
`a=1,b=1`, and total variation
`round(50*Σ|normalize(f_i)-normalize(m_i)|,4)`.
No new model, assumptions about field selection or outcome-driven
probability edits.

| Physical race suffix | Frozen decision (UTC) | Provenance recorded (UTC) | After decision, minutes | Max abs Δ market p (m₀ vs m₁) | Max abs Δ combined p with m₁ | Stored conflict = m₀ replay | m₁ conflict |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `S2_NR_2026-10-09:5` | 17:48:05.933923 | 17:57:30.600616 | 9.411 | 0.01985771 | 0.01141446 | 39.0920 | 36.7790 |
| `MO_NR_2026-10-17:10` | 19:13:44.578730 | 19:25:05.300190 | 11.345 | 0.03734198 | 0.05808288 | 30.5934 | 26.8660 |
| `S4_NR_2026-10-21:9` | 17:49:06.371026 | 17:55:16.220815 | 6.164 | 0.03411454 | 0.03187469 | 36.8344 | 34.7466 |
| `S2_NR_2026-10-22:5` | 17:48:10.971588 | 17:55:05.107694 | 6.902 | 0.03353808 | 0.04096475 | 48.9888 | 46.9859 |
| `S3_NR_2026-10-25:11` | 16:23:07.541767 | 16:34:19.539149 | 11.200 | 0.06779918 | 0.07895829 | 27.7523 | 24.5152 |

Each of the five original saved market inputs yields **exactly 0.0 maximum absolute combined-p difference** against the saved combined values and identical 4-decimal conflict score. Each later odds map yields the differences above. The source of the mismatch is **before the log-pool probability combination**: the later provenance's normalized odds do not equal the original market distribution stored with the decision.

**Late provenance `code_sha` values are part of that late attachment, not independently proven decision-time code identities:**

| Race suffix | Later provenance code SHA |
| --- | --- |
| S2 9 Oct race 5 | `fe00809ce5895b7ba65505b2ccd06906f94ee784` |
| Momarken 17 Oct race 10 | `1f23f06dcb3d3b8f7bb73a9c50268dc953478592` |
| Skive 21 Oct race 9 | `cd1f3aa84a9d3d97bde523c4d6c66cc9ab713c76` |
| S2 22 Oct race 5 | `840d255cbdad75ebb6c39e9ede0c0eb90cf12c34` |
| S3 25 Oct race 11 | `6649325d9d417a3f59e4ba5284c3d338654c8c1c` |

## Bounded causal conclusion and next exact-state test

**Strongly supported first divergence:** source-market/provenance mismatch
introduced by later `decision_provenance.market_odds_json`. The unchanged
formula (power/log pooling and total-variation conflict) correctly reproduces
the original stored numbers from the original persisted market distribution.
**Not established:** whether the discrepancy arose from later market movement,
manual provenance attachment, market-snapshot selection, a past ingestion code
bug, or a subsequent state edit. The historical audit did not pin its SQLite
restore and the candidate does not prove a unique original-timestamp source
snapshot. Therefore `runtime_replay_parity=FAIL` remains correct; modifying
the audit to ignore these mismatches or rewriting source/provenance would be
invalid.

To close: owner-approve a future exact-receipt V1 audit, verify ID/ZIP/SQLite
SHA and audit code identity from *that audit's own uploaded original receipt*;
compare all five frozen rows and source market JSON against contemporaneous
raw `market_snapshots`/provider receipts, then isolate the first *historically
time-valid* divergence. Only a proven implementation error may justify a
separate narrow regression-tested audit PR. No model, BET, PIT, ticket or
settlement write here.
