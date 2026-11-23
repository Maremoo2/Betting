# PREWATCH-004B5 — PIT evidence recovery (NO BET)

Base: PREWATCH-004B4 draft #224 exact HEAD. Ancestors #223, #222,
#221 remain draft/unmerged. No production, Champion, Collector, Ledger,
automation, strategy or bet changes.

## Real originals reused (three separate populations)

1. **2026-11-23 Collector source**: run 45141884691, hash-bound original
   ZIP + source program PDF + actual source_observed_at_utc. The selected
   Färjestad race 5 has 15/15 active runners and five program PDF raw
   history rows per runner. A genuinely captured source before T-4 is
   **not** proof that each row is independently verified official result,
   that the source state was final at T-4 or that each horse has a
   permanent registry identity.
2. **MVP-023B Norwegian official results**: 7 authentic, 2026 DNT
   historical observations, source original SHA, registered DNT horse
   identity and target linkage. All are retrospective research only.
   Their first official history version pre-target cutoff is not
   independently attested; no PIT or model promotion.
3. **M7B2B original availability research**: re-run existing
   `history_availability.run` on pinned archived originals, preserving
   its separate M7B2B PDF-source PIT decisions per cutoff and its
   historical-result-chain decisions. This is a **different cohort**
   and cannot be interpreted as Färjestad horse-level PIT.

## Admission blocker

`admission_originals._REVIEWED_RECEIPTS` is empty. The default HBI
identity admission requires independent reviewed `REGISTRY_BINDING`
and `ATG_HISTORY` originals, exact bytes/hash/URI, actual positive
pre-cutoff observed time, provider game/race and exact active runner.
The B2 adapter returns `PIT_UNPROVEN` by design, and the current B3
and B4 outputs must remain non-model/non-BET.

These checks cannot be satisfied by just adding a plausible digest or
changing a flag. M7B2B permits PIT verification of **observed original
source availability** without attesting complete historical result
semantics, identity or model eligibility.

## Independent next genuine capture

For an upcoming event, let the existing isolated research Collector
persist an immutable original roster, native registration, independent
registry response and original official history response *before T-4*,
with source URI, SHA of exact original bytes, response-completion UTC
clock, start/cutoff clock and an append-only correction record.

A separate human/reviewer checks and pins exact receipts against bytes,
role, source and timestamp; one horse is accepted only if the
target-identity-result linkage is demonstrated. Do not manufacture a
registry document out of current race/PDF data, or use a later fetched
result as the earlier original. Do not assume last-five completeness.

Status: research-only; first genuinely admitted historical target horse
is BLOCKED until such an independently reviewed pre-cutoff chain exists.
The correct next action is source acquisition, not lowering a gate.

## Tests

PR-only original E2E: full 004B..004B5 pytest, Ruff, real Collector
ZIP/SHA, genuine M7B2B archival audit and MVP023B seven historic results,
two runs with byte-identical readback. Ordinary full CI runs separately;
MVP018 missing original archive remains a known separate blocker.
