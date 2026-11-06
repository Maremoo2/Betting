# MVP-023B/P1-D — TEST_ONLY fundamental challenger prototype

**Not an empirical horse-racing result or training authorization.**

\`hbi.mvp023b_fundamental_testonly\` implements a deterministic L2-regularized
full-field conditional multinomial logit, starting all weights at zero and
using fixed full-batch gradient descent. For horse i in race r it computes
\`p_i=exp(w·x_i)/sum_active_horses exp(w·x_j)\`; probabilities are
checked for positivity, finiteness and sum 1. It reuses
\`hbi.research_lab.metrics\` for matched racewise log loss, multiclass Brier
and calibration bins against a 1/N baseline.

The executable input schema is explicitly
\`MVP023B_TEST_ONLY_SYNTHETIC_COHORT_V1\` and **requires**
\`source_scope=TEST_ONLY_SYNTHETIC\` and \`model_eligible=false\`.
No M5/M7B1A real racing dataset, arbitrary archive or 2025/2026 row can
be passed to it. Feature values must be explicit, finite and complete:
unknown histories are not imputed as zero. All active runners must appear
exactly once per physical race, the synthetic winner must be a unique
member, and dead heats/incomplete fields are rejected.

Frozen scientific roles: synthetic 2015–22 development, 2023 internal
validation, 2024 challenger validation. The 2025 candidate lockbox is
forbidden and 2026 is already exposed, not blind OOS. Evaluation race IDs
may never be used in training. No validation-set hyperparameter selection
occurs; fixed learning rate, epochs and L2 are source-visible input args.
Market odds and result/label variables as horse features fail closed.

Run **only with hand-authored TEST_ONLY synthetic JSON**, not real horse data:

\`\`\`bash
python -m hbi.mvp023b_fundamental_testonly \
  --test-only-synthetic /path/to/explicit-test-only-cohort.json \
  --output /tmp/fundamental-challenger-test-only.json
\`\`\`

Output contains a SHA-bound synthetic model specification and synthetic
evaluation metrics by year, with
\`fitted_test_only_estimator=true\` but
\`fitted_authentic_model=false\`,
\`fundamental_fit_ready=false\`, \`benter_fit_ready=false\`,
\`market_only=null\`, \`combined=null\`, \`economic_ev_ready=false\`,
\`bet_authority=false\`.

Before empirical fitting on authentic 2015–22 historical races, acquire
source-replayed prior performances and identity joins for all active
horses, sufficient population coverage, chronological result labels,
scientifically approved semantics, real as-of evidence and no 2025
exposure; repeat matching cohort scoring on a true 2023/2024 OOS split.
Do not weaken PIT to qualify this candidate.

Benter's existing \`hbi.probability.combine_probabilities()\` is
unchanged. No α/β are fitted here. No Champion/CORE004/V3.3.12,
settlement, automations or bet authority changes. Owner review only.
