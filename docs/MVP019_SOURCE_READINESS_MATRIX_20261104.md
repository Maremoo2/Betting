# MVP-019 – original-source readiness matrix (research only)

A new read-only per-race matrix consumes exactly the **same four SHA-checked
original JSON bodies** and independent joins as MVP-016/MVP-018. It creates
no retrospective model freeze, certified PIT observation, price or betting
permission. Historical physical races lacking contemporary collector receipts
are `HISTORICAL_ONLY_NO_CURRENT_SOURCE_RECEIPT`, not `READY_FOR_FREEZE`.

## Fixed authenticated replay

Original source set: [CORE-003 41832416078](https://github.com/Maremoo2/Betting/actions/runs/41832416078),
main `d0bb18d30b27d0ca62f2c74331f52b42ca90a2a1`.
It has **67** physical races, **24** complete historical frozen model fields,
**16** official-result-scored model pairs, **14** WIN triples and **3** current
F1 cohort races. All three source-model input approvals are blocked. The
CI original replay requires four existing original SHA receipts before
MVP-019 tests execute. This is historical original data, not the newest run.

Recent ordinary [CORE-003 41842113458](https://github.com/Maremoo2/Betting/actions/runs/41842113458)
on 4 Nov after #138 reported **68 physical / 24 complete model fields /
19 result-scored pairs / 18 WIN triples / 0 PIT** and
`INCOMPLETE_ORIGINAL_COVERAGE`. Expected 20 model pairs were **not**
observed. Detailed four-race causation still needs original result-row audit.

## Explicit evidence, unknowns and blocker classifications

Per race the report retains original collector startlist SHA, original
admission blockers, reported source clock and T−4 cutoff, known active roster,
ATG fundamentals, current source cohort status and three separate cumulative
model/outcome flags. It does not infer new source capture from cumulative
historical scores. Classification distinguishes identity, ATG full-field,
active roster, source clock, scratch, implementation, and missed cutoff.

The underlying four-source join **does not independently attest each runner's
stable registration ID, an official scratch original or separately evidenced
official start-clock receipt**. Those stay `UNKNOWN`/missing in every
current-race report. A collector research-model eligibility status is not
equivalent to independently audited PIT or actual production model admission.

Historical 27-race original source audit classified **7 ATG, 3 identity,
6 roster, 9 PDF, 1 clock, and 1 T−4** first blockers. These are historical
observations, not evidence of current code defects. Timing/identity source
proof is needed before isolated repair PRs. No source-bypass or hardgate
changes are proposed.

`bet_authority=false`, `pit_certification_performed=false`,
`new_model_freezes_created=0`. No extra automation, scheduling changes,
Champion/CORE-004/V3.3.12 modification or archival write. This branch must
pass Ruff, full pytest and original replay before anyone claims `CI_PASS`.
