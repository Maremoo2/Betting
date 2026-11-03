# DEV-011 – Persistent prospective scorecard coverage (research only)

**Scope:** P0, isolated, independent from MVP-011 and PIT-003A. Baseline main \`f55f3eaa1e3b97aa444a8e1db7c306fc7129092f\`. No betting authority, model retraining, replay rewriting or settlement mutation. The original \`Recover prior original prospective models (read only)\` and \`hbi.core_t4_receipt attest\` workflow steps remain unchanged.

## Reproduced current blocker
Before this PR, DEV-009 loaded \`pit003a-prior-models\`: one GitHub API page (\`per_page=100\`) and only the newest **20** \`bet-mvp-shadow-*\` artifacts. A qualified model first frozen in run 41646155051 (Eskilstuna 2026-11-03 race 8, SHA-256 \`f04dd8f19254764114739009383371e3367c445c917c8fac5b08cf085e814a6d\`) fell out of the rolling window as later model attempts produced empty indexes. GitHub run 41662283155 retains the original DEV-009 official outcome bytes, source SHA-256 receipts and verified winner 5.

## What this PR changes
1. Adds an **independent, scorecard-only** source recovery step after PIT attestation. It uses \`gh api --paginate --slurp\` to enumerate all available GitHub artifact pages, validates \`total_count\`/unique artifact IDs, filters only exact original model and DEV-009 scorecard artifact names from \`main\`, and sorts by source run/artifact ID. Inclusion is independent of historical score, price or outcome. **No latest-N cap.**
2. Recovers each selected original into separate \`dev011-scorecard-models/{run_id}\` and \`dev011-scorecard-results/{run_id}\` directories, never into PIT's original \`pit003a-prior-models\`. Unknown, missing, unavailable or expired sources remain explicit \`INCOMPLETE_ORIGINAL_COVERAGE\`.
3. Adds a checksum-backed \`dev011-coverage/manifest.json\` (inventory source SHA, source artifact IDs, original index hashes, per-model SHA verification, pinned-result errors and complete/blocked counts).
4. Extends the existing DEV-009 scorecard to consume source-verified archived official results. It verifies both original raw HTTP payloads against their archived SHA and per-race metadata, preserves original observation clocks, recovers the original model report by immutable SHA and recomputes Brier/log loss. A conflicting or changed archived result is \`NOT_EVALUABLE\`, not silently rescored from a later response. New races without pinned results can still use the existing read-only official GET.
5. Keeps PIT-certified versus non-PIT research cohort scoring separate, and \`bet_authority=false\` unconditionally. If original coverage is incomplete, aggregate completeness is marked BLOCKED even though separately verifiable individual scores may remain visible.

## Original-based and negative regressions
PR CI separately downloads **original** model archive \`bet-mvp-shadow-41646155051\` and authentic result/archive \`dev009-authentic-original-scorecard-41662283155\`. A real Eskilstuna result is scored with **21 synthetic EMPTY model archives inserted after the authentic source**, without any live results fetching. The original winner #5, model SHA, Champion/CORE-004/normalized WIN losses and original result SHA all remain identical; PIT remains 0 and no stake is created.

Negative tests cover pagination beyond page one, incomplete pages, expiry, missing download, changed original model SHA, missing outcome, tampered raw original, conflicting independently hashed result versions, duplicate race IDs, incomplete CORE-004 fields and prohibited PIT/BET-authority inference. The synthetic empty archives are **test fixtures only**, not fake production records.

## Coverage and constraints
- **Before:** newest 20 prior model artifacts; a prior qualified original excluded after 20+ empty attempts. Latest scheduled DEV-009 scorecards showed 0 actual pairs despite the archived Eskilstuna result.
- **After (test contract):** unbounded original artifact inventory, source-deduplicated race IDs, 1 original verified scored pair retained after >=21 later empty archives. Historical source artifact expiry can still produce \`INCOMPLETE_ORIGINAL_COVERAGE\`; no secret reconstruction.
- **Current field admission blocker is independent:** six unique rejected runs in MVP-012 (FR PDF/starts mismatch 3; ATG full-field/fundamentals 2; ATG/cross-provider identity 1). DEV-011 does not increase new eligible model fields.

## Operational risks / follow-up
A full paginated GitHub inventory and download of archived scorecards can grow in network volume as sources accumulate. This PR does not add a new archival database, background process or new scheduled workflow. Reassess read-only retrieval cost from actual GitHub runtime, and introduce an independently reviewed compact manifest checkpoint only if demonstrably necessary; never fall back to arbitrary latest-N or PIT-origin mutation.

**No merge without owner's explicit approval.** First scheduled \`main\` proof can only be claimed after owner-approved merge and an actual ordinary CORE-003 run uploads \`dev011-coverage-manifest-{run_id}\`.
