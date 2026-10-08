# Rikstoto PRE-WINNER live archive smoke — 8 October 2026

Actual public Rikstoto GETs, not synthetic fixtures. Source architecture:
MSFT-crawler `ac3e30bc4494766c27bb7826ed46a1fd557df88f`.
No production database, Champion, betting thresholds or execution routes changed.

| Scope | Attempted | Full-field accepted | SE | NO | FR | WIN/collective within 60s |
|---|---:|---:|---:|---:|---:|---:|
| 22–26 December 2025, first two applicable races/meeting | 32 | 31 | 14 | 7 | 10 | 8 |
| 1–31 January 2026, all applicable races | 664 | 544 | 229 | 145 | 170 | 92 |

Sample expansion gate passed (31/32 = 96.9%) before January collection. All
31 January dates were observed; no unresolved fetch errors. January accepted
544/664 = 81.9%. Denominator includes races offered in supported collective pools,
not every race on Rikstoto. Secondary/multi-track pools are explicitly excluded.
January rejections: 76 without a complete supported collective pool, 32 with
incomplete WIN/PLACE fields, 12 not normally finished.

Archive stability refetch passed for 16 sample meetings and 104 January meetings,
using the first accepted race's WIN/PLACE/collective payloads in each meeting.
This is meeting-level sample evidence, not a finality certificate for every runner.
Temporary IDs occur in 24 sample races and 399 January races. They permit race-local
market alignment only; these counts do not establish complete fundamental history.

PRE excludes finish positions/winners/dividends and is frozen before POST fetches.
Sample POST: 20 joined, 11 quarantined (10 official results incomplete, one identity
mismatch). PRE file remained unchanged. Known country/display suffixes may be
normalized; an unstable TMP ID plus blank result ID permits race-local matching
only with identical start number and unique name. Contradictory IDs fail closed.

January POST: 366 joined, 178 quarantined (170 official results incomplete,
eight identity mismatches). The 170 incomplete results correspond to all accepted
French races; French market coverage is therefore not complete result coverage.
Matched runner outcomes use 1,286 exact provider-ID/name matches and 2,385 explicitly
race-local start-number/unique-name matches. PRE SHA-256 remained unchanged after
all 544 official result requests. None of these POST joins are live settlement.

Follow-up table/export verification: published result/dividend summaries were fetched
for all 31 sample races and all 544 January races, with no rejected display rows.
This includes the Bordeaux example's WIN 8.70, PLACE 2.40/2.10/3.70 and TWIN 11-3
20.80; it does not override the incomplete official French full-result status.
Separate PRE/POST Markdown, CSV and upload ZIPs are available under each archive's
`exports/` directory. PRE file hashes remained unchanged. Ruff and 261 tests passed
after integration with the latest main branch.

Local reproducible archives (ignored by Git):

- `research-local/rikstoto-pre-winner/historical-sample-v2/`
- `research-local/rikstoto-pre-winner/january-2026/`
- Sample raw-market cache was reused from `historical-sample/`; each extracted row
  records source path, URL, acquisition time and payload hash. The older sample
  was superseded after discovering that `isMerged=true` does not alone invalidate
  an otherwise complete historical Swedish field.

Frozen PRE file SHA-256:

```text
sample:  719fa1a3a7118421b41638ce6c6ad717414e232bbd63e9b2a1ca69886e13b08f
january: d464dbb18cebc9b5f0206cc3c3601680a60dcd5e7a335397090a207e0fffccdd
```

Windows interrupted a checkpoint replacement midway through January with a
transient reader/scanner lock. Bounded atomic rename retries preserve the prior
complete checkpoint; a regression test passed, and the same archive resumed to
completion. Re-running the finished January command reused the verified freeze.

Validation: Ruff passed; 256 tests passed; editable package and installed CLI
tested. Public archive retrieval does not prove executable pre-race PIT prices.
Collective shares can freeze at the first leg while later-leg WIN changes hours
later. No P/L, CLV, PLACE probability or prospective strategy performance is claimed.
Full M0–M6/MOD/EXTREME protocol was not retrievable from the available conversation
reader; those variants remain explicitly NOT_CONFIGURED. The thread's example
winner was already known, so the batch is retrospective even with PRE masking.
