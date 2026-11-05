# MVP-023A P1-B | Source- and time-bound feature coverage (NO BET)

This audit consumes the **existing M5** \`dataset.jsonl\` and its
\`model-readiness.json\` SHA256; it does not create a parallel datastore.

\`\`\`bash
python -m hbi.mvp023a_feature_audit \
  --dataset-dir /absolute/path/to/existing-m5-output \
  --output /absolute/path/to/new-feature-report.json
\`\`\`

Audit output reports every supported/candidate variable, active runner
denominator, exact quality statuses, country/year slices, source-data SHA,
and per-physical-race observed source limitations. It inspects the source
references already imported by M5 but does **not** independently re-fetch
or re-hash the original provider payload. Accordingly it cannot grant PIT
or model training admission from the backfill dataset alone.

The available original M5 schema may provide the pre-race roster's driver and
extra-distance fields. Race placing, km times, purse and any historical outcome
are **retrospective labels only** and are never inferred to be historical
pre-start features. Further candidates (last 3/5/10 starts, normalized
kilometre time, opponent strength, start method, post position, trainer,
gallop/DQ, rest days, class and local surface/track) remain explicitly
\`MISSING\` until authenticated, independently time-verified sources exist.

The audit refuses *before reading dataset.jsonl* if its manifest includes
a 2025 month. The proposed 2025 lockbox stays unread until owner-approved
exposure audit; 2026 Jan–Sep is already exposed and never called blind OOS.
No score, model or Benter weight estimation is performed. All integration
tests are clearly TEST_ONLY synthetic M5-shaped records.

Do not confuse M5 \`identity_status=IDENTITY_VERIFIED\` based on result
reconciliation with cross-provider horse identity at the *prediction time*.
\`TMP\` and copied namespace IDs do not authorize training. Raw originals
and publication-time evidence must be replayed before a \`PIT_VERIFIED\`
historical feature can be granted.

MVP-021, Champion V1.1, CORE-004, V3.3.12, settlement, workflows,
PIT/T-4 and staking are untouched. \`bet_authority=false\`.
