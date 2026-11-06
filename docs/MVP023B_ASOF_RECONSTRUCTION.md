# MVP-023B/P1-C — original-source as-of research audit, not betting PIT

Research model contracts distinguish **three** truths:

1. A verified prior event occurred before the target race:
   \`RETROSPECTIVE_PERFORMANCE_RECONSTRUCTION\`.
2. The *same original provider response bytes*, its stable horse identity
   proof, dated race, actual event clock, original observed/published clock
   and source-version timeline all preceded a registered **T−4 research
   cutoff**: \`HISTORICAL_ASOF_REPLAYED_RESEARCH_ONLY\`.
3. Existing production \`PIT/T−4\` and betting eligibility: **never granted**
   by this tool or by levels (1) or (2).

This module validates literal \`raw-results/<sha256(path)>.json\` archived
provider envelopes and recorded source/published/acquisition SHA, without
network, model fitting, source mutation, or state writes. Historical
source first-published and correction/version clocks cannot be inserted
through a late caller's sidecar: they must also be in the archived
original. A target start timestamp/timezone or prior-event clock that
cannot be independently established blocks level (2), rather than
retro-certifying timestamps. Name/TMP identity matching, cross-provider
namespace guesses, duplicate historical starts, future/same-day events,
2025 result access, market/target labels and source tampering fail closed.

Exact source and target selection is described in a bounded, manually
reviewed JSON manifest with schema \`MVP023B_PRIOR_SOURCE_ASOF_INPUT_V1\`;
example execution:

\`\`\`bash
python -m hbi.mvp023b_asof_audit \
  --manifest /path/to/research-asof-source-manifest.json \
  --source-root /path/to/native-original-caches \
  --output /tmp/mvp023b-asof-audit.json
\`\`\`

This is not an automated upgrade of M7B1/M5 documents. The version
timeline and initial publication receipts are *not present* for the known
seven authentic Norwegian 2026 DNT prior-result examples; as-of VERIFIED
count for those examples stays **0 / NOT_PROVEN**. No genuine 2015–2024
input is included in this PR. Synthetic positive source-envelope tests
are labeled \`TEST_ONLY_HISTORICAL_ASOF_VERIFIED\` and must never be cited
as observed original racing coverage or model readiness.

M5/M6, \`history_availability.pit_decision\`, existing Research Lab model
splits, Champion, production PIT, settlement, wager rules and betting
state are unchanged. \`model_training_eligible=0\`, \`bet_authority=false\`.
Draft PR; no merge without explicit owner approval.
