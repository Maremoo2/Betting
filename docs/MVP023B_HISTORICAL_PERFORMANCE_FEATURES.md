# MVP-023B/P1-B — first horse-performance features from real official originals

## Reproduced genuine original scope

This source-replay path reuses M7B1A's **seven existing, source-verified
Norwegian official prior-start rows**, bound to the original 2026-10-20
Rikstoto target starts by stable \`DNT_REGISTRATION\`, official result race and
date, full original target registration/name, and official DNT HTML member
receipts. The zip is SHA pinned at
\`96d6a3c4a344a61b3d42b8173fff1b02fa44a4c1a430902db559d684960f8eb9\`.
Only explicitly approved 2026 Norwegian original result members are read;
the 2025 lockbox is **not used, decoded, trained or tuned against**.

\`\`\`bash
python -m hbi.mvp023b_performance_features --root . \
  --output /tmp/mvp023b-real-no-2026-performance.json
\`\`\`

This is a **first authentic previous-start performance-feature demonstration**
on an already-exposed 2026 target cohort. The year 2026 is not pristine OOS.
It does not establish an eligible 2015–2024 historical training cohort.
The parent M7B1A original archive spans other sources, but the new replay
opens only registered 2026 NO prior-result members.

## Feature semantics and denominators

Per exact target physical race + target selection + stable horse identity,
calculate from *previous verified official race starts only*:

- Available, verified previous-start sample count. Missing lifetime starts
  are \`UNKNOWN\`, never assumed zero.
- Latest **observed** verified start date gap (not guaranteed last career start).
- Last 3 / 5 / 10 **observed** result codes, their actual sample sizes,
  and win rate among previous starts with supported result semantics.
- Observed win rate and top-three rate with a denominator of only
  verifiable historical result codes. \`UNKNOWN\` is excluded, not counted
  as a loss.
- Original distance and start-method context counts; do not infer the
  target race context. Only compare km time when two or more officially
  measured starts have *identical* recorded distance and method.
- Gallop and DQ rates are \`NULL/MISSING\` if negative-event observations
  are not explicitly supplied. Driver, trainer, opponent strength and
  target-gate context remain \`BLOCKED_SOURCE\`.

Every row carries original individual source SHA, exact historical-race key,
target physical ID, country/track/date and identity namespace. Duplicates,
future/same-day starts, 2025 members, TMP/NAME/ATG-to-DNT namespace
collisions, unknown compound timing codes, unsupported DQ/gallop semantics,
market/outcome inputs disguised as features, and preapproved PIT/model status
all fail closed.

\`qualification=RETROSPECTIVE_PERFORMANCE_RECONSTRUCTION\`;
\`asof_verified=false\`; \`pit_verified=false\`;
\`fundamental_training_ready=false\`; \`bet_authority=false\`.
No first-publication/source-correction clock is invented. Even if the
known historical event occurred prior to the target, that does not establish
historical pre-T4 availability.

## Next source recovery (separate from code-ready claim)

A sufficient development cohort needs 2015–2022 genuine prior performances
for enough distinct target active-field runners and labels; 2023 internal
validation and 2024 late challenger validation are preserved as fixed
research roles. 2025 is an unopened candidate lockbox. A partial, honest
retrospective dataset can grow one month at a time through P1-A, but cannot
claim PIT or executable WIN odds, and this initial sample cannot be used
to fit production or empirical OOS Benter weights.

This PR does not modify M5/M6 parsers, canonical models, CORE-004, Champion
V1.1, production thresholds, settlement or HBI state. No merge authorized.
