# MVP-023A · Historical coverage & eligibility (read-only)

This is **not** a new crawler, training job or model. It extends the existing
\`rikstoto_crawler.archive\` / M5 research chain with a deterministic *audit* of
archives the owner supplies. Source IDs, SHA, historical result labels and
PIT-frozen features are separate concepts.

## Run on existing unpacked native archive

\`\`\`bash
python -m hbi.mvp023a_historical_coverage \
  --root /absolute/path/to/research-local/archive-2015-2025/full \
  --output /absolute/path/to/new-output/coverage.json
\`\`\`

The root may contain \`inventory/YYYY-MM.json\`, \`market-days/YYYY-MM-DD.json\`,
\`result-days/YYYY-MM-DD.json\`, \`raw-markets/<sha256(path)>.json\`,
\`raw-results/<sha256(path)>.json\` and
\`weekly/YYYY-Www-MARKET.zip\`. The CLI does **not** fetch new data or modify the
root, and the output is exclusively created (cannot overwrite an earlier report).

The engine validates monthly inventory canonical-body hashes, physical race IDs,
daily market checksum, weekly market manifest/member hashes, result-to-market
freezes, source/origin/receipt hashes, exact runner rosters and official complete
result originals where present. It re-derives normalised full-field WIN from
archived odds before classifying it complete. It deduplicates inventory metadata,
rejects duplicate frozen physical races, and never substitutes an unavailable
original with a synthetic record. Output includes race-level independent quality
booleans, blockers, year/month/country/track summaries and exact denominators.

**Important:** Counting a historic weekly ZIP as a market archive does not make
its *raw original sources* present. If the raw cache is absent, the output still
records source-chain blockers. A valid timestamp must be offset-aware; sentinel
start clocks and later provider updates remain unverified. An original provider
horse registration that does not start with TMP is not an independent
cross-provider identity proof. Historical results are labels, never features.

## Scope and missing source prerequisite

The repository documents a 2015–2025 metadata census of **202,946 entries**
and a bounded **55-race pilot**, but those values are not inputs or default
coverage counts for this CLI. The original multi-year unpacked archive resides
outside the repository. To produce meaningful year-by-year coverage the owner
must supply or run against the **actual archive root**, including original raw
envelopes and monthly inventory files. A report from an empty or pilot-only
root explicitly describes **that root only**, not all Norwegian/Swedish racing.

The **2025 candidate lockbox is withheld by default**: 2025 result-day files are
not opened, parsed or hashed, and their count appears only as
`2025_lockbox_result_files_not_read`. The 2025 inventory and market-only
metadata may be counted, but cannot yield a verified result or training label.

All PR tests use **TEST_ONLY synthetic source-shaped fixture files**. They are
integrity/regression cases, not authentic race evidence and do not establish a
usable training sample. No 2025 lockbox outcomes are opened for tuning.

## Readiness and next steps

- \`PIT_MODEL_ELIGIBLE\` is **never automatically granted** by this v1 audit.
  The old archived market/result formats do not independently attest
  pre-race availability of full historical performance features, cross-provider
  identities or a prior frozen model. These require their own authoritative
  source receipts, identity approval and time-contract validation.
- \`MARKET_PRE_RACE_VERIFIED\` requires exact full-field WIN, original receipts
  captured before conservative T−4, and per-runner updates before cutoff.
  This is a market-source quality flag, **not** model or BET permission.
- The readiness section returns \`BLOCKED_SOURCE\` for fundamental fitting and
  Benter weights until independently verified historical feature and OOS
  prediction inputs exist. Economic EV is \`BLOCKED_TIME\` until executable
  pre-decision odds and settlements are independently attested.
- The separate next deliverable is a per-feature historical audit reusing
  \`hbi.backfill\` feature evidence and \`hbi.research_lab\` time contracts.
  Reuse \`hbi.probability.combine_probabilities\` later; do not choose weights.

Frozen governance: Champion V1.1, CORE-004, V3.3.12, PIT/T−4, existing workflows,
settlement and betting rules are untouched. Research-only; \`bet_authority=false\`.
