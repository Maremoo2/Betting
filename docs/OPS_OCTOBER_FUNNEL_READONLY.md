# OPS-P0 | October Pre-Watch funnel reconciliation — read-only

**Decision:** Prioritize operational evidence before more model or parser features.
This is the first diagnostic deliverable from the October 2026 operational
audit. Frozen Pre-Watch **V3.3.12 (8 Oct–8 Dec)** remains unchanged.

## Independently read from the connected live dashboard

Read-only inspection of **Betting V3.3 – Prospective Ledger** on
**27 October 2026**:

| Primary tab / metric | Observation |
| --- | ---: |
| PreWatchFunnel, 15–27 Oct | **168 distinct exact race IDs** |
| `SCREENED_BELOW_THRESHOLD` | 138 |
| `PARTIAL` | 29 |
| `#REF!` formula error | 1 |
| Numeric scored races reaching 70 | **0** (max 69) |
| Numeric scored races scoring 65–69 | **42** |
| Numeric scored below mispricing 18/30 | **131/138** |
| Numeric scored below liquidity 8/15 | **137/138** |
| PreWatchPreflight source rows | 158 |
| RunLog source rows | 235 **runs, not races** |
| MarketSnapshots source rows | 79 **runner observations, not races** |
| FrozenDecisions | 1 `NOT_EVALUABLE` |
| ProbabilitySnapshots | 0 data rows |

The first 33 PreWatchFunnel entries are near sheet rows 2–60; **135 more
rows reside at sheet rows 1501–1635**. Reading only the first 500/1000
rows gives an incorrect coverage conclusion. This audit covers all 168
nonblank IDs, not just the first page of the sheet.

**Coverage caveat:** The PreWatchFunnel ledger first contains 15 Oct; 12–14
Oct run observations in RunLog **do not prove** corresponding per-race
frozen decisions, and 1–11 Oct were **not audited here**.

## Interpretation that must not be corrupted

- A liquidity component score below **8** is **not evidence of a measured
  small separate WIN pool**. A V75/V85/V65/V86 combined pool, public shares,
  historical pool or unknown quote is **not** a contemporaneous standalone
  WIN pool with source timestamp. Report missing observation separately.
- A mispricing component below **18** is not proof that no valuable win price
  existed. Source-backed historical race shape / trips and an independent,
  frozen fundamental p(win) must be assessed separately.
- A `PARTIAL` entry is not forced into a numeric zero or scored.
- The old `#REF!` row remains a formula-error status and is excluded from
  score denominators. It must not silently be repaired or reinterpreted as a
  new historical decision.
- A recorded near-threshold (`65–69`) score is **research triage only**,
  **not** A-WATCH, a locked minimum price, a calibrated p(win), or BET.
- A repeated run, preflight or individual-runner market snapshot is **not**
  another distinct race. No fuzzy joins across spelling, country or race
  numbers. Post-start preflight data is excluded from pre-start evidence.
- 235 RunLog rows are distinct **logging attempts**, not 235 screened races;
  summarizing `identified_races` as a unique count would be incorrect.
- 42 near-threshold races are **diagnostic**, not a representative sample of
  successful bets and must not lead to retrospective score changes.

## New diagnostic CLI

`hbi.prewatch_october_audit` accepts a **private local export of exact
Google Sheets tabs** as CSVs and produces a new report outside the repo:

```bash
python -m hbi.prewatch_october_audit \
  --export-dir /private/ledger-csv \
  --from-date 2026-10-12 \
  --through-date 2026-10-27 \
  --output /private/OPS_OCTOBER_READONLY_AUDIT.json
```

Required exports: `PreWatchFunnel.csv`, `PreWatchPreflight.csv`,
`MarketSnapshots.csv`, `FrozenDecisions.csv`,
`ProbabilitySnapshots.csv` and `RunLog.csv`. Optional:
`RaceInventory.csv`, `PreWatchSelectionAudit.csv`. Preserve the
**entire PreWatchFunnel tab, including physical sheet rows 1501–1635**.
Each CSV's SHA-256 is included in the report for independent reproduction.
The command refuses to overwrite an existing report.

Report output includes every original frozen race ID with a **single**
terminal status, its unmodified score, component diagnostics, exact-key
prestart preflight observation counts, known market snapshot counts,
probability and decision joins, and a **42-row near-threshold priority
queue** sorted by the original frozen score. It does not copy models,
submit wagers, use market shares as WIN liquidity, or alter any Sheet,
collector, database or saved score. The `prestart_full_field_WIN_self_declared_groups`
field is a diagnostic self-declaration only: it NEVER verifies hardgates.

**Acceptance checks:** repeatable totals matching the source-export SHA;
same exact race IDs and scores on rerun; no duplicate primary race keys;
detect stale/poststart/missing clock, unverified separate pool, formula
errors, score/field arithmetic mismatches and contradictions between
A-WATCH status and frozen score; do not infer p(win)/fair odds or BET.

## Next P0 blocks after the reconciliation

1. **Complete 42-race source-failure table**: classify original liquidity
   evidence as `UNKNOWN_OR_PROXY_NOT_MEASURED` or
   `SELF_REPORTED_CURRENT_WIN_POOL_UNCORROBORATED`. This is source
   triage, never quantitative proof of low volume. Manually examine
   relevant frozen candidate source citations and independent price
   hypotheses; no historical backfill.
2. **Phase B contract test**, first on an explicitly synthetic, nonbetting
   fixture: demonstrate full-field same-race identity, current scratches,
   individual WIN pool / per-runner quotes, as-of freshness, probability
   freeze, conservative price gate and full-funnel transitions. A synthetic
   successful test is **not** an actual A-WATCH/BET.
3. **Prospective real event**, *only if* a qualifying frozen A-WATCH
   arises and complete authoritative live evidence exists. Otherwise
   continue to record `PASS`, `PARTIAL` or `BET_BLOCKED`.
4. **Evaluation after freezing**: maintain distinct log-loss, Brier,
   calibration, closing line value, settlement and realized P/L. Keep
   WIN and V4X payout/pool economics separate.

Unrelated DATA-004F PDF gold-review work remains open but is **not**
the binding operational obstacle identified by this audit.

## Governance

The script never changes V3.3.12 thresholds (70 total, 18 mispricing,
8 liquidity), source hierarchy, probability-estimation rules, staking
(25 NOK WIN), A-WATCH watcher, Phase B hardgates or scheduling.
It makes **no external writes**. The canonical SQLite/HBI database
remains the source of truth; this dashboard audit does not certify
global production completeness. `BET_BLOCKED` is explicit.
