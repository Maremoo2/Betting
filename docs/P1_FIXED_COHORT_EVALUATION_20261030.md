# P1 – Fixed-cohort paired probability evaluation contract (research-only)

**Purpose:** A future market-vs-Champion-vs-CORE-004 comparison must use the exact **same frozen physical racing cohort** and winner for all three models. No result-based race deletion, late addition or after-the-fact protocol revision is acceptable.

## New implementation

`scripts/p1_fixed_cohort_evaluation.py` ingests three **separately captured immutable files**:
1. `--protocol`: the literal protocol file, hashed SHA-256, must equal the frozen manifest hash;
2. `--manifest`: an *explicit pre-declared ordered list* of all physical race IDs, experiment ID and `protocol_registered_at_utc`;
3. `--records`: full-race WIN probability maps and outcome for each declared race. Uses existing `prospective_eval_gate.validate_cohort()` for T−4 freeze, original source lineage/PIT claims, same selection sets and future/outcome rejection.

Every declared race ID must appear exactly once. Any missing, duplicate, post-declared extra or blocked race **suppresses all aggregate model metrics**. That avoids a biased 'only complete races' success claim. The script calculates ordinary multiclass log loss, multiclass sum-Brier, paired candidate-minus-market/champion differences and day-level means only for the complete claimed cohort.

**Crucial:** The existing gate accepts boolean `roster_pit_certified`/`source_publication_attested` claims; a JSON file by itself does **not** prove their truth. Neither files nor local clocks independently prove the source was registered before the race; the GitHub commit/audit log would need independent attestation. Hence even an internally passing hypothetical cohort has status `EXPLORATORY_CLAIMS_ONLY_UNATTESTED` and `p1_validated=false`, `model_promotion_authority=false`, `betting_authority=false`, always.

A descriptive 30-day check is informational only: **not a powered OOS trial, not a CI=profit criterion**, and not a method to retroactively promote retrospective 297-race data. A fully pre-registered minimum independent sample/power study, original source/publisher timestamps, split audit, full market odds and fees, cluster uncertainty and explicit HQ review remain separate gates.

## Current implementation milestones

| Gate | Status |
| --- | --- |
| Frozen schema, original bytes SHA-check, exact declared denominator | Coded with negative regression tests |
| Same per-race market/Champion/candidate probabilities and winner | Coded / claims-only |
| Aggregate metrics on complete synthetic cohort | Unit-tested, research-only |
| Historical 297 races retrospectively recast as untouched OOS | **FORBIDDEN** |
| Original source/PIT independent proof and pre-race immutable registration | **MISSING** |
| CORE-004 fitted independent market-free features | **NOT FITTED** |
| 30+ prospective monitored days and preregistered power | **NOT AVAILABLE** |
| BET/ROI or Champion promotion | **OFF/NOT AUTHORIZED** |

Related [P1 issue #90](https://github.com/Maremoo2/Betting/issues/90) and [CORE-003 source #83](https://github.com/Maremoo2/Betting/issues/83). Under no circumstances should this script write results to the real P1 Ledger or change V3.3.12/Champion/25 NOK stakes.
