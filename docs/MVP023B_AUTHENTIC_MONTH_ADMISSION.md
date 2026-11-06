# MVP-023B/P1-A — read-only original-month admission (2015–2024)

This is a **real executable importer/acceptance shim** for the *existing*
\`rikstoto_crawler.archive\` layout, not a second crawler, not a copied source
archive, not a result-label generator, and not a production database importer.

## Run one source month without reading any other month

From the repository root, with the owner's local archived originals mounted
read-only (no need to upload all 132 months):

\`\`\`bash
python -m hbi.mvp023b_archive_admission \
  --root /path/to/research-local/archive-2015-2025/full \
  --month 2019-06 \
  --output /tmp/mvp023b-admission-2019-06.json
\`\`\`

For a historic month with **only** packaged MARKET weekly ZIP and no day file,
supply an exact native-week file. **Every day within this ZIP must belong to
the admitted month**, otherwise fail closed. The original ZIP is never
extracted into the owner's archive directory:

\`\`\`bash
python -m hbi.mvp023b_archive_admission \
  --root /path/to/research-local/archive-2015-2025/full \
  --month 2019-06 \
  --weekly-zip weekly/2019-W23-MARKET.zip \
  --output /tmp/mvp023b-admission-2019-06.json
\`\`\`

For another month, choose another output path; the output is write-once.

The shim only stages \`inventory/<month>.json\`,
\`market-days/<YYYY-MM-DD>.json\`, \`result-days/<YYYY-MM-DD>.json\`,
explicitly-selected MARKET weekly ZIPs, and **exact** SHA-addressed
\`raw-markets\`/\`raw-results\` caches referenced by those selected days. All
staged content stays in a disposable private temporary directory. It reuses
\`hbi.mvp023a_historical_coverage.build_coverage()\` to validate source
envelopes, SHA digests, physical IDs, full-field/scratch integrity, frozen
market/result linkage, official result members, and historical clock
limitations; no reimplementation of source verification is trusted.

Output: \`schema=MVP023B_NATIVE_MONTH_ACCEPTANCE_V1\`, the SHA256 and relative
path of every **actually read** original, manifest digest, bounded missing
original refs, per-country/per-track physical race and verification counts,
and non-negotiable \`bet_authority=false\`, \`model_training_eligible=0\`,
\`benter_fit_eligible=0\`. Missing raw originals are **reported**, not
imputed. Discovery-only rows are **not** called usable training records.

A source root may physically contain the 2025 lockbox; the shim only selects
the explicitly specified 2015–2024 month, never enumerates other months'
results, never reads 2025 raw caches through legitimate original references,
and rejects out-of-month references. ZIP file paths, symlinks, duplicate
physical races, missing/corrupt source hashes and foreign-month content fail
closed. Unknown historical markets, program identity, lifetime history,
publisher-first-publication clocks and executable odds remain **unknown**.

## Reusing M5, not building another dataset loader

For month-sharded immutable collector-native ZIPs, use the existing M5
\`HBI_BACKFILL_INPUT_V1\` format (\`format=CRAWLER_NATIVE_ZIP\`), with real
\`path\` and raw ZIP \`sha256\`, and run:

\`\`\`bash
python -m hbi.cli backfill --manifest /path/to/selected-months.json \
  --output /tmp/mvp023b-selected-months-m5
\`\`\`

Then use the *existing* \`hbi.mvp023a_feature_audit\`,
\`hbi.mvp023a_dataset_partitions\`, and Benter readiness hardgates.
The archive acceptance and M5 importer are separate audited input modes:
a native archive directory is **not** automatically an M5 ZIP.

**Source availability:** On the verified repository main of 2026-11-06, the
documented 132-month/202,946-entry census and 55-race pilot are descriptions
of an offline owner collection, **not accessible original files** in
the repository. The authentic M4/M5 2026 cohort is a different SHA-verified
39-race source and is not rebranded as 2015–2024 training data. Unit tests
using 2020 source-shaped records are \`TEST_ONLY\`.

No owner consent to merge; no model fitting or production policy changes.
