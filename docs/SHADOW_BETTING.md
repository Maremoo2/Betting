# Shadow betting protocol

Shadow mode simulates decisions and settlement without submitting a real wager.

## Immutable ticket rule

A shadow ticket is frozen at decision time. It records the product, selections,
available price, fair price, estimated edge/EV, paper stake, model version, source
snapshot and actual time-to-start. Results may be appended later, but the original
decision is never rewritten.

`NOT_EXECUTABLE` is a valid research result. Typical reasons include:

- no independent fundamental probability
- incomplete full-field alignment
- unavailable market snapshot
- unsupported product probability model
- unavailable or ambiguous settlement contract

## Five-minute watcher and T-4

GitHub Actions invokes the read-only watcher every five minutes during the local
Rikstoto watch window. For a race roughly 1-8 minutes away it:

1. restores the latest canonical HBI state;
2. refreshes the Rikstoto raceday;
3. captures available V/P/TV/T market data and the canonical Rikstoto runner field;
4. if the T-4 target is a few minutes ahead, waits inside the job;
5. captures a fresh market snapshot at best-effort T-4;
6. records actual timing/latency;
7. runs the shadow decision layer;
8. checkpoints SQLite and publishes the new state artifact.

GitHub scheduling is not a low-latency execution venue. A delayed runner can miss the
ideal T-4 timestamp. HBI records that miss instead of backdating the decision.

## Current autonomous decision scope

Vinner is the first executable shadow product because V3.2 already has a horse-level
p(win) architecture and a directly observable single-selection market price.

The watcher now generates that market-free FUNDAMENTAL distribution automatically
from `FUNDAMENTAL_CHAMPION_V1_1`. Rikstoto `/starts` defines the field; Swedish
trot runners may be enriched with market-free ATG lifetime history. The model uses no
odds or betting percentages and is allowed to feed the paper-betting layer only when
its history-coverage gate passes. Norwegian field-only races currently fail that gate
and remain `NOT_EXECUTABLE`.

The initial shadow combination policy is explicitly named
`SHADOW_RESEARCH_V1_EQUAL_LOG_POOL`. Its equal fundamental/market weights are a
research baseline, not a validated Benter coefficient estimate.

Plass, Tvilling and Trippel market observations are collected so the project can learn
their market structure without pretending that p(win) automatically gives the correct
product probability. Historical multi-leg program endpoints are disabled by default
after live 404 verification.

## Nightly settlement

At 00:30 Europe/Oslo the nightly job reviews the completed previous local racing day.
It restores the latest state, fetches official result/final-odds data where the
contract is understood, settles eligible tickets, and writes a daily report.

The report includes:

- committed and settled paper stake
- gross return and net P/L
- ROI on settled stake
- ticket/settlement/win counts
- positive-CLV count
- product breakdown
- NOT_EXECUTABLE count

Vinner uses official final win odds plus the complete result. Plass settlement is
implemented only when the official final place-odds map for the race is present.
TV/T/DD/V4/V75 and related products remain pending until official payout/dividend
contracts are verified.

## State safety

All workflows that mutate the SQLite artifact share the GitHub Actions concurrency
group `hbi-state-writer`. A writer therefore performs:

`restore latest -> mutate -> checkpoint -> upload new state`

without another HBI state writer racing it and uploading an older database.
