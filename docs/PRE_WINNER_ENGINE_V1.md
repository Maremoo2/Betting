# PRE-WINNER Engine v1.0

The `pre_winner` module processes frozen Rikstoto PRE archives mechanically. It accepts any number of weekly PRE ZIPs or crawler archive directories. It produces research evidence only and never opens POST files, chooses a blend, estimates PLACE probabilities, or creates decisions/stakes. Existing operational betting and Champion are unchanged.

## Run and upload

```powershell
python -m pre_winner --input research-local/rikstoto-pre-winner/january-2026-weekly-v3/exports/weekly --output research-local/pre-winner-engine-v1/new-run
```

`--input` also accepts multiple explicit PRE ZIP paths or archive directories. Directory discovery selects only `Rikstoto_PRE_*.zip`; POST ZIPs are ignored. The installed equivalent is `pre-winner`. Use a new output directory for every run; existing nonempty output cannot be overwritten.

Upload one `PRE_WINNER_BULK.zip` to the analysis thread. It contains:

- `PRE_MASTER.csv`: one active horse / race / independent collective pool observation, including provenance and identifiers.
- `PRE_SIGNALS.csv`: the same columns, restricted to non-NONE signals. Diagnostic observations remain explicitly labeled.
- `PRE_QC.json`: rejected races, conflicts, duplicates, coverage counts and aggregates by week, date, track, country, product and time class.
- `config_v1.json`: frozen rules and configuration hash.
- `MANIFEST.json`: source PRE hashes and coverage manifests, plus output file SHA-256 hashes.

Raw archives stay locally in their existing weekly organization. Source manifests retain rejected races, missing days and collection scope; accepting a race never implies complete discovery of that country's calendar.

## Frozen rules

Both conditions must pass. Classify most extreme first; every observation receives exactly one signal.

| Signal | Delta | R |
| --- | --- | --- |
| EXTREME_POS | >= +0.075 | >= 1.50 |
| STRONG_POS | >= +0.050 | >= 1.25 |
| MOD_POS | >= +0.025 | >= 1.15 |
| EXTREME_NEG | <= -0.075 | <= 0.67 |
| STRONG_NEG | <= -0.050 | <= 0.75 |
| MOD_NEG | <= -0.025 | <= 0.85 |

Otherwise NONE. Delta is a probability fraction (0.05 = 5 percentage points). A 1e-12 comparison tolerance handles floating-point boundary representation, following existing V3.3.

WIN normalization uses `(1/odds)/sum(1/odds)`; collective normalization uses `share/sum(shares)`. Only the whole active field contributes. Normalization and robustness calculations import existing pure V3.3 helpers. The exclusive tier classifier is importable as `pre_winner.signals.classify`.

The largest absolute WIN/COL timestamp difference across the active field determines pool time class: PRIMARY <=60 seconds, SECONDARY >60 to <=300, EXCLUDE_DIAGNOSTIC >300. Classes never get pooled for confirmation labels.

ROBUST_CORE means all four V3.3 sensitivity corners pass for a positive or negative STRONG signal: delta 4/6 pp with positive R 1.20/1.30 or negative R 0.70/0.80. BORDERLINE means some corners pass but not all. These labels are threshold sensitivity, not a probability estimate or proof of predictive value.

DUAL_POOL_STRONG requires at least two distinct products supporting the same horse in the same race and time class, with STRONG_POS or EXTREME_POS. COL_CONSENSUS is POSITIVE/NEGATIVE for at least two strong products in that direction, CONFLICT if both directions appear, otherwise INSUFFICIENT. Multiple pools of the same product make the panel AMBIGUOUS_DUPLICATE_PRODUCT and prevent dual confirmation. Diagnostic panels can carry these labels but remain excluded from primary analysis.

## Integrity and isolation

Require archive V2 metadata and matching source policy hash, explicit scratches, complete active WIN/PLACE/COL fields, unique horse identities, finite prices/shares, coherent product/leg/pool/race mapping, consistent stored normalization, timing and provenance. Invalid races are quarantined, reported, and make CLI exit 2. Unreadable archives or incorrect PRE hashes abort processing. Exactly identical race records are deduplicated; conflicting snapshots quarantine the whole race. Observations are sorted deterministically and never depend on batch size or outcomes.

Historical market archives are not live decision snapshots. Same-date checks do not certify that the source snapshot occurred before start. Acquisition time and market update time remain separate. A small WIN/COL skew does not establish prospective availability. Swedish PLACE quality flags remain evidence only; PLACE semantics are not inferred.

The manifest explicitly says `prospective=false` and `post_read=false`. January had already been crawled with a separate POST stage before this engine was created; January is retrospective acceptance, not a blind validation batch. Future PRE registers must be frozen before opening their POST results. Do not alter v1 rules after inspecting outcomes; changes require a new version and prospective protocol.

## Acceptance

See [2026-10-08 acceptance report](PRE_WINNER_ENGINE_V1_ACCEPTANCE.md). Tests cover tier boundaries and AND rules, batch invariance, duplicate/conflict handling, complete fields, scratch exclusion, time boundaries, distinct-product cohort confirmation, forbidden POST inputs, hash validation and immutable outputs.
