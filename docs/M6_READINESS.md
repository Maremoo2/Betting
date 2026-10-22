# M6 — Swedish identity and chronological model preparation

Research only, NO/SE. Based on main `7a7637064ee5d920c8fa3cff6e60041e6606d96a`, which already merged M5 PR #42. This PR depends on #42; it neither merges nor repeats M5. Monthly archives remain on HQ's PC and have not been searched for, reconstructed or collected.

## Actual identity evidence

Original program archive: `tests/fixtures/rikstoto-2026-10-20.zip`, SHA256 `a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e`.

All 208 Swedish horses in 19 archived fields have TMP registrations **in the original Rikstoto starts responses**, not IDs invented by the collector. Driver license values such as `ATG53023` identify drivers, not horses. Swedish PDF biographies document age, sex, sire and dam. They do not supply permanent horse registrations.

Bounded, read-only requests through the existing AtgClient retrieved the calendar and exactly these 19 race payloads. The archived source is `tests/fixtures/atg-se-2026-10-20-identity.zip`, SHA256 `a053ce855c230c8e10450dfcecca3447873718512269bfc2b132c2d66f84745c`. Its manifest pins each original JSON envelope (URL, actual observation timestamp, HTTP status and complete provider payload); hashes refer to archived envelope bytes, not raw HTTP bytes. No monthly backfill or new crawler was created.

```sh
hbi resolve-se-identities --date 2026-10-20 \
  --archive tests/fixtures/rikstoto-2026-10-20.zip \
  --sha256 a2d9c1b5fd08946c55433fe346a28860bf7721a79ed7e6099dc716b498bdbb6e \
  --atg-archive tests/fixtures/atg-se-2026-10-20-identity.zip \
  --atg-sha256 a053ce855c230c8e10450dfcecca3447873718512269bfc2b132c2d66f84745c \
  --output /tmp/se-identities.json
```

Actual summary: 19 races, 208 horses, 0 original stable registrations, **196 IDENTITY_VERIFIED, 12 UNRESOLVED**. The 12 belong to Eskilstuna race 5: ATG says `monté`; this resolver requires `trot` and records `RACE_METADATA_CONFLICT`. No discipline coercion is performed.

Example: Bergsåker race 1, number 1, Rajadhiraja retains its original TMP registration and is corroborated as `ATG_HORSE:758929` using exact calendar/race/track/full-field names and numbers **plus age, sex, sire Maharajah and dam O.F.V.Princess**. This is not a name-only match. Ambiguous fields, duplicate normalized names/IDs and conflicting biographies fail closed. Normalization handles accents and punctuation only; no fuzzy spelling merge occurs.

All links are **RETROSPECTIVE_IDENTITY_ONLY**. ATG was observed after the target race. This improves retrospective corroboration from 0/208 to 196/208, not pre-race identity coverage, Rikstoto registration coverage, historical-start linkage or live provider admission. Full source payloads include post-race/market fields; the resolver only reads identity, race metadata and biography, and never exports result/market values as features. No TMP registration is replaced, and no historical start is automatically merged on name.

## M5 dataset extension and real audit

M5 `dataset.jsonl` now contains a versioned `model_candidate` per race, alongside the original roster, source references and **separate labels**. There is no new datastore. Inputs expose identity, driver, trainer, distance, start method and history with explicit missing/PIT flags. Track and race time remain race-level fields. Missing history is unknown, not zero starts. A later observation or a claimed publication date cannot establish pre-race availability; feature source hash/URL/observation must match the recorded provenance and precede the race.

The initial history feature definition is deliberately **not validated**. Candidates remain ineligible and the output explains this. Outcome/market feature names are not approved. No model-training, provider, FFQ1, V3.3 or frozen Pre-Watch policy changes are made.

```sh
hbi backfill --manifest examples/backfill/m4-regression.json --output /tmp/m6-research
hbi model-audit --dataset-dir /tmp/m6-research \
  --protocol examples/model-protocol.json --output /tmp/m6-audit.json
```

Actual regression cohort: 39 NO races, 393 roster runners; 4 independently result-verified fields and 41 active raw labels (25 positive numeric placings). Audit: NO 39 in test, SE 0; **data_ready=0, metrics=null, training_performed=false**. This is the unchanged M4/M5 source cohort, not a monthly backfill demonstration and not the Swedish identity cohort. Never combine their denominators.

## Next week's monthly archives

Create a local M5 manifest using `schema: HBI_BACKFILL_INPUT_V1`, a descriptive `cohort`, and `archives` entries with `format: CRAWLER_NATIVE_ZIP`, actual `path` and SHA256. The native collector ZIP must satisfy M5's existing inventory/cache/integrity contract. A calendar month name alone is not evidence of collection completeness.

```sh
hbi backfill --manifest /absolute/path/selected-months.json --output /tmp/monthly-research
hbi model-audit --dataset-dir /tmp/monthly-research \
  --protocol examples/model-protocol.json --output /tmp/monthly-audit.json
```

Use new output paths. Batch output gives per-month import, identity, label and PIT counts; audit gives each race's chronological partition and exact exclusion reasons, separately for NO/SE. Retrospective result fetch times are accepted for labels, never as proof of feature availability. This sequence performs no training.

## Evaluation preparation and explicit remaining work

The executable data protocol fixes train 2015–2023, validation 2024 and test 2025–2026; intervals must be chronological/disjoint and whole races stay together. Dataset bytes are checksum-checked and duplicate races rejected. These example boundaries are a documented research choice, not a performance-selected split.

The scoring primitive reuses existing HBI log loss, summed multiclass Brier and calibration bins. It rejects nonfinite, out-of-range, boolean, partial-field, wrong-cohort and non-normalized probabilities. A uniform 1/N baseline uses the identical scored cohort. Synthetic examples exist only in tests, marked TEST_ONLY; no synthetic metrics are claimed as model performance. Prediction quality has no economic return calculation.

**Not delivered as empirical evaluation:** no validated history feature contract, fitted model artifact, leakage-audited fit provenance, prediction-file ingestion or country-specific empirical score report exists yet. The CLI therefore runs data controls only and reports metrics NOT_RUN. Before enabling empirical scoring, bind model artifact, training/validation race IDs, protocol and dataset hashes; prevent any test fitting/tuning; validate feature cutoffs and full-field labels; evaluate matched NO/SE test cohorts and document calibration uncertainty. The scoring primitive alone is not that gate.

No p(win), WATCH or BET is enabled. Status: **M6_PARTIAL**: Swedish identity and reproducible data controls demonstrated; complete empirical-evaluation interface and validated history inputs remain unfinished, and the real monthly archives are not yet available. Rollback: revert this PR; research outputs are disposable and production is unchanged.
