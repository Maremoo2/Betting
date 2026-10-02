# V2.1 Contender Gate

V2.1 is a decision-completeness control, not a new probability model. Champion,
combination weights, value thresholds, stake and the one-Winner-bet cap are unchanged.
The existing engine already values the complete aligned field. The gate now checks
that those assessments really exist before a frozen Winner conclusion or paper bet.

## Mandatory pricing

Screen every active runner. Require pricing if any condition holds:

- System share **>= 8 percent**, expressed as `8`, not `0.08`.
- Winner decimal odds **<= 12**.
- A documented sporting signal or model/market discrepancy.
- Missing Winner odds or system share: conservatively require pricing rather than
  assuming a missing screen means a non-contender.

Every required assessment needs a finite `p_win` in `(0,1]`, matching unrounded
`fair_odds = 1/p_win`, a finite `minimum_odds >= fair_odds`, explicit
`BET/WATCH/PASS`, and a timezone-aware pre-decision `priced_at`. An absent or
invalid assessment blocks finalization with `UNPRICED_CONTENDER`.
Do not fill a missing probability with market share or an invented estimate.
Screen inputs cannot enter the fundamental model; they only require review.

## Automatic Winner path

`run_win_shadow_decision` runs the gate after full-field/PIT eligibility and the
existing probability/value calculation, but before selecting tickets or declaring
PASS. All runners are priced, including those outside the one-bet allocation cap.
The effective minimum price respects both existing safety-margin and minimum-edge
requirements; neither threshold is changed.

At finalization, a BET requires a quote no older than **120 seconds**, not from the
future, and a decision within **5 minutes** before the start. A missing, stale,
early or below-minimum price downgrades BET to WATCH. It never changes probability
or creates a stake. Exactly the minimum price passes. An already started race blocks.
These are execution-quality controls, not evidence of profitability.

Every completed gate audit, including rejected ones, is stored in `provider_payloads`
under `CONTENDER_GATE_V2_1`, keyed to the frozen decision run. It contains triggers,
probability, fair/minimum price, original/final decisions, quote time, and reasons.
If only WATCH opportunities remain, the frozen decision is WATCH with
`CONTENDERS_AWAIT_PRICE_OR_REVIEW`, not `NO_VALUE_BET`.
Earlier eligibility failures remain NOT_EXECUTABLE and do not manufacture pricing.
Existing frozen decisions remain immutable: WATCH is an audit outcome, **not** a new
automatic later retry or order-execution loop. There is no real-money execution.

## Separate coupon review

HBI does not currently build automatic V4/V65 tickets. The supported manual/research
entrypoint reviews one complete active race field and its proposed coupon leg:

```sh
hbi review-contenders examples/contender-gate.json --output contender-review.json
```

Run this for every leg before declaring the complete coupon ready. Exit code `2`
means blocked; exit code `0` means this supplied leg passed the gate. Review all leg
reports; one passing leg cannot certify an entire coupon. Input is a supplied
pre-race research snapshot, not independently live-verified by this command.
The automatic Winner path separately retains its provider full-field/PIT gates.
The command writes a JSON audit to `--output`; it never submits bets or invents p(win).

`ticket_selections` is optional: omit it for a Winner-only review. An empty list is
an empty coupon leg, not a disabled consistency check. Any originally BET-rated
runner absent from that leg gets `BET_ABSENT_FROM_COUPON`, even if its late price
subsequently collapses. Supply a nonblank explanation in `omission_reasons` keyed
by selection to resolve the blocker; the alert and explanation remain visible.
Being selected on a system coupon never implies a Winner BET, and vice versa.

The example uses synthetic probabilities for a compact three-runner test field;
it is not an actual reconstruction of the full Emmeline race. The regression uses
12.5% system share and 7.78 Winner to prove mandatory pricing, not to establish a
prospectively available 15% probability. Post-race analysis must not be backfilled
into historical frozen decisions.
