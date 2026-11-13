# P0 Research Ledger

Offline, read-only journal for the physical race denominator declared in an externally pinned DEV-009 scorecard. Requires the original scorecard ZIP and indexed CORE-003 artifact ZIPs named by artifact ID.

```bash
python -m hbi.research_ledger --originals /private/originals \
  --scorecard /private/originals/13361697131.zip \
  --index-sha 53974e4466406016ed86d7b67111f2c54325bae9352618aba131501130c17008 \
  --output /private/new-research-ledger.json
```

DEV-009 chooses the latest eligible freeze using time and original SHA independently of market coverage and outcomes. The journal checks that selection against the pinned DEV-009 freeze history. It rehashes the selected model and cohort index, applies the existing field/market/result gates and recalculates scores. Unavailable alternative freezes are represented by their pinned index metadata. The historical clock contract is preserved. This export grants no prospective or PIT qualification.

`HBI_RESEARCH_LEDGER_V1` contains one sorted record per physical race, a primary stopping reason in diagnostic order, overlapping blockers, source references, vectors and paired scores. Null indicates unavailable information. The pair population includes all verified Champion/CORE-004 pairs. The triple population uses exactly the same races for all three metrics. The original inputs are read-only and the output is created exclusively. For a future declared cohort, create a new ledger with its own pinned index. Preserve earlier exports and their input hashes.

## Replay of 4 November originals

Input scorecard ZIP SHA-256 `e60cef8e94fe0d8da49e1dc3402bfef4999cea96bc6025f289b0fa51e6c489f9`. The local source set initially yielded 30 triples and no pair-only record. Recovery of 14 additional original model ZIPs enabled the complete baseline reconciliation. Output SHA-256 `2df3b56cff7220b0b5f137ecc4fd917cfdc9b3b089e4b7317805eecbb7681da8`.

89/89 physical races, 39 complete model fields, 32 result-verified model pairs, 31 same-freeze WIN triples, 57 blocked, zero PIT. Filtering the replay to the previously frozen First30 IDs reproduces the following.

| Model | Log loss | Multiclass Brier |
|---|---:|---:|
| Champion | 2.12908725033343 | 0.8614155898208863 |
| CORE-004 | 2.0876948876149384 | 0.848072764111595 |
| Normalized WIN | 1.9491062640456285 | 0.8235196459130825 |

The sample is selected by source availability and provides exploratory predictive scores.

## Next coverage work

1. Preserve indexed model originals for all declared races. 36 rows lack a verified freeze. Require every observation to have a verified original or explicit disposition.
2. Improve full-field inputs. 14 rows report model not ready, eight lack a frozen field and six have invalid vectors for each model. Counts overlap. Preserve failed attempts and avoid imputing probabilities or identity.
3. Verify the official-result chain and same-freeze WIN. One race has conflicting result receipts, one has a late scratch and three have incomplete finish. One verified pair lacks same-freeze WIN. Preserve competing original revisions and keep unresolved races blocked.
