# Betting V3.3 — active betting standard

V3.3 replaces V2/V3.2 at the betting decision boundary. Implementation lives in
`src/betting`, separate from HBI research/evidence ingestion. HBI/PRE-WATCH records
remain evidence; the bridge cannot write odds, probabilities, decisions, stakes,
settlement or Champion. No change to the frozen Champion model, parameters,
historical decisions, settlement or original October comparator cohort.

## Usage and ownership

Install with `pip install -e ".[dev]"`. Register BEFORE the next blind batch:

```sh
betting register-batch forward-v33-001 --output batch-v33-001.json
betting review pre-race.json --batch batch-v33-001.json --output decision-001.json
# Equivalent active decision entry point:
hbi review-betting pre-race.json --batch batch-v33-001.json --output decision-001.json
betting reassess decision-001.json late-quote.json --output opportunity-002.json
betting closing decision-001.json closing-quote.json --output closing-001.json
betting coupon decision-001.json coupon-leg.json --output coupon-leg-001.json
betting stake decision-001.json stake-request.json --output stake-001.json
betting multi-race reviewed-legs.json --output coupon-001.json
```

Output paths must be NEW; existing decisions/registrations cannot be overwritten.
Invalid input writes a BLOCKED report and exits 2. Store these files with the batch
artifacts before any result is observed. The policy hash travels with every decision
and re-entry. A batch registration records current UTC, frozen policy and no tuning.
Retrospective demonstrations/tests are not validation evidence. Do not merge V3.3
records into the original Champion forward cohort or use this batch to tune thresholds.

The existing scheduled watcher remains an explicitly labelled **frozen research
comparator**, not a V3.3 betting approval. There is no calibrated automatic interval
or PLACE producer yet. V3.3 requires those separately supplied model outputs and
blocks finalization when they are missing. Do not fabricate bounds around Champion
or turn historical top-three frequency into `p(place)`. This update provides the
active decision interface, not a claim that production now generates calibrated
intervals, PLACE estimates or validated betting profits automatically.

## Pre-race input contract

See `examples/betting-v33.json` for a synthetic complete-field example. It is a
schema fixture with deliberately artificial probabilities, never live evidence.

- `active_field`: exact unique active selection IDs; `identity_matches` must cover
  all with status EXACT, confidence 1 and unique nonempty provider IDs.
- `fundamental`: model version, `market_free=true`, observed/priced timestamps,
  full-field `probabilities` of `p_low <= p_mid <= p_high`. Midpoint sum is 1,
  lower/upper totals must bracket 1. Estimates must exist before decision time.
  No automatic uncertainty estimation or interval calibration is claimed.
- `cases`: every selection has explicit `qualified` boolean, independent reason
  and minimum price at least `1/p_low`. This input is the sports/model case,
  never an automatically generated market-support classification.
- `decision_snapshot.WIN`: race ID, immutable snapshot ID, observed UTC, all odds.
  `pWIN=(1/odds)/sum(1/odds)`. Zero, missing, infinite or <=1 odds fail closed.
- `decision_snapshot.collective`: independent named pools, each containing all
  shares, timestamp, race ID, snapshot ID and canonical `product` equal to its pool
  name. Normalize each pool separately.
  Incomplete/stale/noncontemporaneous pools are explicitly unavailable, not neutral.
  Require quotes <=120 seconds old, pool/WIN skew <=60 seconds and decision within
  the final 300 seconds before start. Post-start opportunities are prohibited.
- `place`: independent market-free model version, observed/priced timestamps,
  full-field marginal interval probabilities, integer `paid_places`, explicit
  cases/minimum prices, and a separate PLACE odds snapshot. Midpoint sum must
  equal paid places; lower/upper totals bracket it. This is not derived from WIN.
- Missing PLACE pricing blocks finalization for an independent qualifying case or
  a positive collective signal. No PLACE payout or settlement is invented.
- `hbi_evidence` is echoed only. A score or market rejection never changes p(win).

## Frozen market evidence

For each complete contemporaneous pool, Δ=pCOL−pWIN and R=pCOL/pWIN.
STRONG_POS requires Δ>=0.05 AND R>=1.25. STRONG_NEG requires Δ<=−0.05 AND R<=0.75.
`DUAL_POOL_STRONG` means positive strong signals in at least two named pools.
`COL_CONSENSUS` is POSITIVE/NEGATIVE for at least two strong signals in that direction,
CONFLICT if any positive and negative strong signals coexist, otherwise INSUFFICIENT.
Pools must be independent product identifiers; duplicate copies of one pool are not
independent corroboration. Correlated pools still are not independent statistical tests.

Sensitivity convention, frozen before batch: delta 4/6pp, positive ratio 1.20/1.30,
negative ratio 0.70/0.80. ROBUST_CORE passes all four corners in one direction;
BORDERLINE passes any corner but is not robust. These ranges are explicit initial
implementation choices, not inferred from winners. The supplied 5pp/1.25/0.75 core
thresholds remain unchanged. Record a NEW policy/batch if future research changes
the sensitivity definitions; never retune this batch after outcomes.

Divergence is supporting evidence only. It cannot create a probability or BET.
An independent qualifying case with negative support requires a written conflict
explanation for finalization, without automatically converting BET to PASS.

## Singles, snapshots and stake

CASE_PASS closes a nonqualifying case; higher odds alone cannot reopen it.
PRICE_PASS preserves an otherwise qualifying case with re-entry price. BET requires
a fresh late price >= minimum AND positive conservative EV (`p_low*odds>1`). Exactly
fair at the lower bound is not a BET. Missing/stale/early quotes produce WATCH.
Reassessment writes a new opportunity linked to the original decision ID and retains
all original probabilities and case eligibility. It never rewrites a frozen decision.
Closing snapshots are separate research records; adding closing prices leaves the
decision ID, original quote, probabilities and decisions unchanged.

WIN and PLACE are separate decisions in each runner row: inspect both for WIN,
PLACE, WIN+PLACE or PASS expression. `allocate_stake` is a separate paper allocation:
one BET = 1u = 25 NOK, all other statuses = 0; there is no 2u discretion. All outputs
are SHADOW_ONLY and no API submits wagers or changes settlement.

## Coupon layer and shadow combination

`review_coupon` runs after complete single reviews. Every omitted >=10% p_mid horse,
BET horse or STRONG_POS horse requires a cut reason. Banker selection must be the
sole included horse, have an explicit explanation, and retain full-field midpoint
and lower-bound pricing plus cut audit. No unvalidated numerical banker cutoff is
invented. `construct_multi_race` combines only passing legs and reports rows/cost;
it does not auto-pick selections or claim coupon EV without joint probabilities.

Optional `shadow_weights` must be preregistered using `register-batch --shadow-weights
weights.json`; each race must match these frozen batch weights exactly. They specify
fundamental/WIN/collective weights
in [0,1] summing to 1, with at least one usable collective pool. This initial linear
research blend uses fundamental midpoints, normalized WIN and mean normalized pool
shares. The weights are recorded; no default is guessed. Its output NEVER affects
single decisions, stake or execution. Prospective validation and a separately
approved promotion are required before any monetary use. Existing governance remains.

## Verification

Run `ruff check .` and `pytest -q`. Regression tests cover threshold boundaries,
full-field/identity/PIT failures, PRICE_PASS re-entry, immutable closing/decisions,
independent PLACE, fixed paper stake, conflict review, cut/banker audit, pool timing,
and shadow blending without decision changes. Synthetic tests are not a live-smoke
claim; existing provider-live-smoke checks remain separate ingestion verification.
