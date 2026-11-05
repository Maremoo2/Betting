# MVP-023A P1-C | Immutable research dataset partition manifest

This research-only adapter extends the **existing M5 backfill dataset**. It does
not re-scrape, refit or replace the M5 importer or Research Lab. It reads the
original SHA-pinned \`model-readiness.json\` and \`dataset.jsonl\` and emits
three write-once files:

- \`manifest.json\`: exact physical race IDs, partition names and SHA digests,
  country/race/runner counts, and blocked training readiness.
- \`fundamental-inputs.json\`: active field and only source-bound, whitelisted
  M5 driver/extra-distance facts, with explicit nulls for missing data.
- \`retrospective-labels.json\`: independent, separately stored result labels.
  Labels and terminal market data are NEVER copied to fundamental inputs.

Run only on an owner-reviewed existing M5 output, e.g.:

\`\`\`bash
python -m hbi.mvp023a_dataset_partitions \
  --dataset-dir /absolute/path/to/verified-m5-output \
  --output-dir /absolute/path/to/new-research-dataset
\`\`\`

Each named physical race and each runner within it must be unique; source
references must include SHA and timestamp. The existing M5 model-candidate
contract must say \`data_ready=false\`, because historical career-feature
PIT evidence is still incomplete. The adapter does not claim these research
files are training inputs or successful model predictions.

Chronological roles are **2015–2022 development**, **2023 internal validation**,
**2024 challenger validation**, **2025 potential lockbox (not opened)** and
**2026 exposed material (not blind OOS)**. The M5 manifest is examined before
reading the source dataset. If any 2025 month is present, the entire operation
aborts without opening the dataset, pending owner exposure review.

Remaining blockers: actual multi-year original M5 archive on owner storage;
cross-source horse identity; verified pre-event publication and source timestamps
for historical performance features; complete prospective WIN; frozen OOS
predictions and independent evaluation receipts. Thus \`model_training_eligible=0\`
**for this adapter**, not a claim about the entire sport/archive.

All code is read-only except the exclusive new research output directory.
MVP-021, Champion V1.1, CORE-004, V3.3.12, PIT rules, settlement, workflow and
betting authority stay unchanged. No production betting or promotion.
