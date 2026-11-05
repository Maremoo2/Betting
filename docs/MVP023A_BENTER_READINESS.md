# MVP-023A P1-D | Benter combination fit readiness

This is a **research-only contract audit**, not a Benter model fit or a
backtest. It reuses the existing HBI implementation
\`hbi.probability.combine_probabilities()\` unchanged. The combination
weights \`alpha/beta\` are deliberately **not estimated or assigned**.

\`\`\`bash
python -m hbi.mvp023a_benter_readiness \
  --bundle /absolute/path/to/owner-reviewed-research-bundle.json \
  --output /absolute/path/to/new-readiness-report.json
\`\`\`

The input is a research object with \`schema=MVP023A_BENTER_READINESS_V1\`,
\`plan\` (registered features and chronological test period),
\`fundamental_model\` (authenticated model/training/prediction bundle SHA, exact
2015–2022 training race IDs and \`uses_market_features=false\`), and \`races\`
(unique physical race IDs, common active field, source receipts, original
frozen prediction SHA and the pre-T−4 market).

The existing \`research_lab.audit_race()\` validates all active runners,
timezone-aware feature event/availability times, prediction distribution,
market distribution and complete official outcome. This P1-D wrapper adds
checks for a non-overlapping training cohort, non-market fundamental features,
T−4 market/fundamental observation and publication evidence, and 2025
candidate-lockbox exclusion.

**Critical:** A self-reported JSON SHA / clock is not independent
authentication of original raw bytes, the provider publication-time history,
or actual model training. This v1 audit therefore **always** requires
\`IMMUTABLE_RAW_ORIGINAL_REPLAY_REQUIRED\` and returns \`NOT_READY\`. It
does not promote a model or grant fit authority merely because synthetic
fields pass schema validation. None of the old historical terminal market
records are considered executable or sufficient for economic EV.

All tests are \`TEST_ONLY\` structural and adversarial cases. Real readiness
requires an authoritatively replayed immutable training dataset, historically
prior true fundamentals, PIT and independent identity attestation,
OOS fundamental predictions, full-field pre-race WIN and frozen chronological
validation. The potential 2025 lockbox remains unopened.

Champion V1.1, CORE-004, V3.3.12, PIT hardgates, WATCH/BET/PASS, settlement,
production workflows and \`bet_authority=false\` remain unchanged.
