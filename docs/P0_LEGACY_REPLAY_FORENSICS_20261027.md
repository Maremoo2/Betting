# P0 | Legacy replay provenance forensics (27 October 2026)

**Mode:** Read-only forensic diagnostic. **Frozen Betting V3.3.12, all past decisions, payout accounting and BET gates unchanged.** No historic data update is authorized by this report.

## Source and reproducibility
- Downloaded actual HBI state artifact `hbi-state` ID `12738404230` from [Shadow Watcher run #40515090668](https://github.com/Maremoo2/Betting/actions/runs/40515090668), recorded 2026-10-27 13:47 UTC.
- Artifact ZIP SHA-256: `584f9351d48f31b17a3f9540937740c26d0a21578775d6ed492a298b2d0fca90`.
- Extracted `data/hbi.sqlite` SHA-256: `973c3661df0b06a72572c1dc0aae08664bc73df343b9245444bf3125751065b7`.
- SQLite connection opened `mode=ro&immutable=1`. No table writes. Recomputed using existing `evaluate_race` contract: normalized market inverse odds, normalized weighted log pool and the original fundamental probabilities and policy JSON.
- **635** frozen decision runs, **264** with the complete replay inputs; **259** matched saved provenance, **5** failed saved-provenance replay. All **five** had original market rows available at exactly `source_market_observed_at_utc` and all reconstructed **combined probabilities within 1e-12** plus **exact model/market conflict score** from the original snapshot.

## Frozen decision vs stale provenance

| Physical race ID | Old saved-market max absolute p-delta | Exact-source p-delta | Exact-source conflict delta | Result |
|---|---:|---:|---:|---|
| `RIKSTOTO:S2_NR_2026-10-09:5` | 0.01141446 | 6.94e-18 | 0 | Source reconstructed |
| `RIKSTOTO:MO_NR_2026-10-17:10` | 0.05808288 | 0 | 0 | Source reconstructed |
| `RIKSTOTO:S4_NR_2026-10-21:9` | 0.03187469 | 0 | 0 | Source reconstructed |
| `RIKSTOTO:S2_NR_2026-10-22:5` | 0.04096475 | 0 | 0 | Source reconstructed |
| `RIKSTOTO:S3_NR_2026-10-25:11` | 0.07895829 | 5.55e-17 | 0 | Source reconstructed |

For each of these five decisions, the stored `decision_provenance.recorded_at_utc` occurs **6–11 minutes after** the original `source_market_observed_at_utc`. Saved-provenance odds differ on **every listed active selection** relative to exact-source odds. Source snapshots have the exact same runner set as the original decision for all five.

**Causal conclusion:** In all five, the source timestamp market alone exactly reproduces the frozen decision. Late odds previously overwritten into `decision_provenance` explain the V1 mismatch. [Already merged PR #53](https://github.com/Maremoo2/Betting/pull/53) prevents this path for future decisions by inserting provenance once and resolving the exact timestamp; it does **not** rewrite or clear historical errors.

## Separate settlement blocker

At source snapshot, one historical shadow ticket remains open:
- `ticket_id=a55a504a-bc34-487d-aced-75326dcb2b59`
- `race_id=RIKSTOTO:S4_NR_2026-10-14:6`; **selection #8**; paper stake 25 NOK; `SHADOW_BET`.
- The local `outcomes` table reports winner **#5** dated 2026-10-14 22:36 UTC.
- This creates a settlement-audit failure after the grace period, but local `outcomes` alone is **not** proof of all conditions used by the official settlement client (complete participant list, participation/finishing status, published winning dividend).
- Existing `settle_open_shadow_tickets` checks these additional gates and must not infer a loss for an ambiguous scratched/absent participant. Investigate provider return/retry and preserve original evidence. Do not force a `-25` receipt without the underlying result contract.

## New diagnostic

`python -m hbi.legacy_provenance --db data/hbi.sqlite --output legacy-replay-diagnostic.json` re-checks saved-vs-original evidence with read-only SQLite URI and classifies:
- `LEGACY_LATE_PROVENANCE_SOURCE_RECONSTRUCTED`
- `UNRECONCILED`
- exact saved-provenance replay matches.

The report status is always `DIAGNOSTIC_ONLY_NOT_PRODUCTION_CLEARANCE`, not PASS. **The existing V1 system audit remains FAIL** until a separately approved, source-audited historic reconciliation decision.

## Explicit stop conditions
- No automatic historic backfill/update, DB write, retroactive PnL, market override, strategy adjustment, or BET reopening.
- No lowering data/market safety gates, no synthetic `p(win)` or fake odds.
- The source snapshot files are production research artifacts; do not commit raw HBI state or private payloads.
