# PREWATCH-004B: original-bound, fail-closed historical features

Status: research-only; DOES NOT certify verified official historical results for the
23 November 2026 full-day Collector cohort. Zero verification is NOT zero
performance. Next stage must acquire independently bound, point-in-time official
historical result originals and verified stable horse identity.

## Reuse, not a new parser

| Existing component | Actual function | Evidence/authority | Reuse in 004B |
|---|---|---|---|
| Collector daily, pdf_program, source_quality | Source PDF + starts, physical races and extracted historical cells | Captured/unverified; reconciliation as-of-capture, no independent PIT | Existing P0 verified source packs |
| Collector history_shadow | PDF raw-line ownership, no accepted gold | Research shadow; does not authorize model | Diagnostic reference only |
| Collector prewatch_handoff | Structured raw source handoff | Source-only | Indirect, via P0 packs |
| HBI collector_handoff | Original archive requests, SHA and PDF/starts identity | Original/PIT conditional read | Existing importer |
| HBI cloud_run002_import | SourceRace + source-only immutable release verification | Source-ready only; no model/BET | Existing P0 build |
| HBI history_semantics | Research adapter: date/track/cells, non-positive-code safety | EXTRACTED, not independently verified; PIT_UNVERIFIED | Yes, through normalize_prior |
| HBI history_quality | Source-bounded pilot report and missing evidence | Research only, reviewed frozen cohorts | Audit reference only |
| HBI historical_intelligence_v2 | Independently hashed ATG prior race results with exact horse ID and temporal gate | VERIFIED only when original/published/observed before cutoff | Gating standard for future source adapter, no Nov23 authenticated matching corpus supplied |
| HBI mvp023b_performance_features | Authenticated NO 2026 research replay for exposed cohorts | RETROSPECTIVE_ONLY, specifically no historical PIT or 2025 lockbox proof | Statistical policy reference; NOT blindly joined to Nov23 |
| HBI cloud_run004_enrichment | Opt-in research fundamental enrichment from live provider | Provisional ID match; no immutable PIT/production approval | Not invoked |
| HBI horse_identity | Validated stable identity via authenticated registry and result original | Strict independent proof required | Identity admission standard; no guessing from names |
| HBI prewatch004_pack | Immutable source-run/PDF/starts SHA, active roster, raw prior lines | 26 source-candidate races and 284 listed entries in Nov23 original | Direct input |

## What 004B adds

- Re-validates original daily ZIP and .sha256 through existing P0 pack builder.
- Binds exact raw lines, candidate date and SHA to the corresponding physical
  race, official runner number and original PDF structured programme.
- Replays existing HBI research semantic adapter without new parsing logic.
  It deliberately uses an empty track dictionary to avoid inventing identities.
- Reports full-field and active-field denominators separately, raw history
  1/3/5/10 counts, research semantic/distance extraction counts and explicitly
  printed gallop/DQ indicators. These are source *candidates*, not official
  verified historical result observations, nor verified absence of an event.
- Keeps verified wins, top3, last-3/5/10 result distributions, class/distance
  performance, verified gallop/DQ rates, permanent horse ID as UNKNOWN until
  independent original evidence is bound.
- Rejects future/same-day history, duplicated source raw rows, mismatched
  race/horse identity and altered source SHA. Does not interpret missing date
  or marker as a zero. Snapshots observed before start do not by themselves
  prove publication/decision-cutoff PIT certification.
- Writes immutable JSON contexts and whole-day coverage, with SHA/readback.
  Re-run with identical original produces identical bytes; revision requires
  a separate run/output directory.

The input contract for a future per-race AI DRAFT is
PREWATCH004B_RACE_FEATURE_CONTEXT_V1; the existing
PREWATCH004_PHASE_A_DRAFT_V1 output is unchanged.
A valid source context alone MUST NOT authorize FULLY_ASSESSED, Champion freeze,
WRITE_CONFIRMED, A-WATCH, BET, p(win), EV, or stake.

## Real all-day acceptance

PR-only workflow .github/workflows/prewatch004b-original-pr.yml pins
Collector original workflow run 45141884691 for 2026-11-23. It is separate
from the production Collector and Betting workflows.

The genuine source archive P0 baseline is 26 source-discovered physical races,
284 listed runners. The 004B PR workflow must independently reproduce these
counts, print raw/semantic coverage with ACTIVE and LISTED denominators,
write one authentic feature pack for each race, compare all SHAs and rerun
with byte-identical readback.

Coverage against an independently verified NO/SE official all-day calendar
remains UNKNOWN. A P0 raw source label does not prove full-day publication or
official previous result availability. Zero independently verified historic
results in this isolated Nov23 input is a **source deficiency**, not a claim
that such historical originals never existed elsewhere.

## Future blockers and release criteria

P1 historical sports evidence should not be marked READY_FOR_REVIEW until
stable target-to-historical-horse identity and SHA-authenticated official
prior-result originals with genuinely pre-cutoff observation/publication are
available for a meaningful share of the day. Then re-use
historical_intelligence_v2.verified_past_race and history_coverage, not raw
PDF rows as model truth. Independently audit event flags, uncovered last-N
history indices, race distance/start method comparability, negative flags
and semantic ambiguities.

Separate known unrelated full-CI blocker: P0 run #45215359090 failed when
five old Nov2 bet-mvp-shadow artifacts were unavailable; no test removal,
synthetic replacement or gate weakening is authorized. Recheck current CI
on the actual PR head and report independently.

No production workflows, Collector parser, active scheduled Pre-Watch,
Champion thresholds, market odds, ledger, live stake, or API keys changed.
