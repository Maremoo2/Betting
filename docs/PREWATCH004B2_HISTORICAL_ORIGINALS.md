# PREWATCH-004B2 — Historical Originals, Identity and PIT (NO BET)

## Scope and exact base

- Based on PREWATCH-004B draft PR #221 HEAD `733543ed00038e338e0045907e4b3fd69950ed80`, not `main` (004B is **unmerged**).
- P0 PREWATCH-004 #220 is already merged on main.
- Isolated draft branch. No changes in `Maremoo2/rikstoto-program-collector`, active scheduled Pre-Watch, Sheets ledger, Champion, betting and production workflows.
- The real 2026-11-23 Collector original used in the PR-only pilot is run `45141884691`, original ZIP+SHA; P0 and 004B validate physical races and field identity.

## Exactly what existing components already prove

| Existing component | Useful functionality | Authority limit |
|---|---|---|
| `prewatch004_pack`, `prewatch004b_features` | Authentic ZIP + SHA, PDF/start-field identity and source-line SHA, 26 physical races | Fullfield/source only; no full historic result semantics |
| `horse_identity.resolve_model_identity` | Original-bound cross-provider target->horse identity, source role, exact snapshot | `admission_originals._REVIEWED_RECEIPTS` currently EMPTY, so no real identity currently passes |
| `atg_admission_source.verify_history_original` | Original ATG response validation, source hash, exact race+ID, as-of cutoff | Does not establish permanent target identity or complete prior results by itself |
| `historical_intelligence_v2.verified_past_race` | Original ATG result payload parsing, result/field/horse ID verification and observed/published bound | Has `pit_certified=false`; publication-only and late fetch do not prove production PIT |
| `historical_intelligence_v2.history_coverage` | Original/horse ID dedup and declared completeness for last 5/10 | Distinguishes observed subset from actual last N |
| `mvp023b_performance_features.run_authentic_research` | **Seven real 2026 official Norwegian DNT prior-starts**, original ZIP/member hashes and stable DNT registration | Retrospective research only; targets from exposed Oct 2026, not independently Nov23 bound or pre-cutoff PIT |
| `history_availability`, `history_feasibility`, `mvp023b_asof_audit` | Source-time/correction research and event clocks | No license to retroactively assert as-of observation |
| Collector `history_shadow` | Raw PDF-line ownership | No independent official result gold |

No new crawler, PDF parser, result-code decoder or model is introduced.

## Newly implemented adapter

`hbi.prewatch004b2_original_binding` provides:

- `bind_target_horse`: first checks the exact P0+004B source hash, full-field identity, official original's observation vs cutoff and prestart schedule. Uses **existing** `resolve_model_identity` with independent reviewed original receipt evidence. A name, number, provisional ATG ID or dynamic provider response alone cannot resolve identity. For resolved target identity, reuses `verified_past_race` for each authenticated original; no direct caller's historical dict is accepted as a result.
- `aggregate_official_history`: pure derived observed-sample features from already-verified individual HBI result rows. Rates use only measurable observations; unknown gallop/DQ is excluded, not zero. Last-3/5/10 is UNKNOWN unless original-history-index completeness is independently attested. Historical results and feature refs retain source URI and denominator. No strength/odds/market inference.
- `make_day_unresolved_report`: completely offline, reruns authentic 004B full-day source/field verification, hashes source contexts, produces an immutable readback audit for all currently unqualified targets. Absence of admitted identity is a limitation of **this input and its verified original set**, not proof that a horse has no prior racing.

Every output remains research-only with `model_eligible=false`, `bet_authorized=false` and `pit_status=PIT_UNPROVEN`; the upstream `historical_intelligence_v2` validator does not grant production PIT and this adapter does not override it. Fullfield DRAFT, freeze, A-WATCH and Ledger are out of scope.

## Authentic acceptance (not synthetic coverage)

PR-only job `.github/workflows/prewatch004b2-original-pr.yml`:

1. Replays seven exact **genuine** DNT Norwegian 2026 official prior-starts through repository-pinned original archive and existing research workflow.
2. Uses the original Nov23 Collector ZIP+SHA and the existing full-day 004B source verifier.
3. Builds `identity-coverage-20261123.json` twice, checks exact byte-identity, verifies 26 unique source-discovered physical races, 284 listed, 275 active, 275 unique horse/race keys, explicit missing identity/PIT and no model authorization.
4. Publishes both immutable research outputs as a short-lived GitHub artifact. Does not publish personal secrets, create new live requests or access a 2025 lockbox.

The DNT original case proves that authentic horse-performance result aggregation is technically available in HBI, but **not** that any of its seven cases can be used as PIT-verified Nov23 targets. One genuine positive retrospective example and an actual blocked Nov23 case are expected; no false positive PIT-verified Nov23 example should be fabricated.

## Current admission blockers and next development

- Reviewed registry/source pins must exist for exact target runner -> permanent cross-provider horse ID and earlier official result original version **captured before the actual decision cutoff**. The current admission pin set is empty.
- Collect and independently validate first-preserved observation version, correction history and complete index (not just five printed raw PDF lines), without retrofitting later API contents into a past timestamp.
- Add documented `PIT_VERIFIED` only through a separately reviewed immutable receipt chain that genuinely meets M7B2B/M7B2C evidence standards; do not edit existing HBI admission gates or approve model/bet authority in this PR.
- An independent complete NO/SE all-day calendar denominator has not been proven by the Collector source quality module.
- CORE/Legacy full CI may fail unrelatedly when five earlier `bet-mvp-shadow` historical source artifacts are missing. Recheck the *exact* PR HEAD, document the difference and do not waive the test.

All newly computed sample numbers are observed-only and non-predictive. This PR does not prove an improvement in Phase A coverage, calibration, positive EV, win probability, or a production-ready parallel analyzer.
