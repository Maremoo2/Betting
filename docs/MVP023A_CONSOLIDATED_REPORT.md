# MVP-023A P1-F | Consolidated historical research report

A **single read-only** status report assembled from the independently
generated artifacts in P1-A, P1-B, P1-C and P1-D. It does not open raw racing
data, turn 2025 into a test set, train a model, or fit Benter weights.

\`\`\`bash
python -m hbi.mvp023a_research_report \
  --coverage /absolute/path/to/coverage.json \
  --features /absolute/path/to/feature-audit.json \
  --dataset /absolute/path/to/research-dataset/manifest.json \
  --benter /absolute/path/to/benter-readiness.json \
  --output /absolute/path/to/new-consolidated-report.json
\`\`\`

Every input report is SHA256 hashed and required to carry its exact
source schema and \`bet_authority=false\`. Internal coverage and feature
report data digests, the dataset's partition member SHA and cumulative
race denominators are checked. Contradictory readiness/lockbox/training claims
cause a hard failure.

Output contains 2015–2026 rows, separate source and runner denominators,
quality category counts, feature missingness and Benter readiness. **A year
without authenticated input observations is \`null\` / \`NOT_MEASURED\`, not
zero.** 2025 result counts stay \`null\` / \`LOCKBOX_WITHHELD\`. M5, historical
census and current prospective cohorts are not silently blended; even when
the same year appears in multiple reports, the scope is labeled.

The builder does not compute a portfolio return or infer that a historical
terminal odds price was available by T−4. \`READY_FOR_FIT\` and \`PIT\`
cannot be manufactured from aggregate stats. The original 2015–2025
multi-year archive must be available separately for meaningful real coverage
reports; synthesized test fixtures are \`TEST_ONLY\`.

This is a downstream report component. It does not replace the four underlying
PRs, and must not be merged before original source-admission and parent PR
review. Champion V1.1, CORE-004, V3.3.12, settlement, automations,
PIT hardgates and betting authority are unchanged.
