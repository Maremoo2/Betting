# P0-SETTLEMENT-001 – official start/scratch status for place-zero runner

**Bounded research-only expansion of PR #88.** The original Rikstoto HTTPS GET results and winner dividend are now independently sourced, but the selected horse #8 has `place=0` and `kmTime=0,0`, which cannot be automatically classified as a valid losing participant.

## Immutable primary evidence from 30.10

[Original source-only run 41123021265](https://github.com/Maremoo2/Betting/actions/runs/41123021265), metadata-only GitHub artifact **13009875389**, receipt SHA-256 **23c665695af9fbd28f2ffe51e10e1fb644f49655ea8521de33dd60c091849a27**.

- Original `raceresults` HTTPS HTTP 200; body SHA-256 **604aba1c6edee3c824231d9acac43a6db11475d6fc16018304292168d9b79ff6**.
- Original `completeresults` HTTPS HTTP 200; body SHA-256 **d7034fce01a75b64e74004c66c59bdf8bb31208cc0bfa56766eae54a5be2e2f4**.
- Winner **#5**, approved `Dividends` WIN payout **6.28**.
- Selected **#8** exists once in complete results: `place=0`, `kmTime="0,0"`, `odds=31`, no explicit `scratched` or `status` on that result row.
- `settlement_source_review` accurately returns `ZERO_FINISH_NOT_PROVEN_DISQUALIFIED_PARTICIPANT` and NO bookkeeping authority.

## This research-only follow-up

New bounded `--probe-start-status` option adds exactly **two more GETs** to official historical `/racedays/S4_NR_2026-10-14/starts` and `/scratched`; the workflow publishes only HTTP metadata, one runner's `isScratched` flag when a unique original entry exists, and whether the same number is explicitly in the race-specific scratched list. Unknown/unparseable shape is reported as **UNKNOWN**, never as `not scratched`.

Even an official `isScratched=false` is an as-of read of that endpoint and does **not** by itself prove race participation, completion, DNF or payout entitlement. This follow-up never writes SQLite, calls settlement, changes P&L or sets permission flags.

### Review/acceptance

1. Original GET HTTP status and response hashes must be observed, or status remains unavailable.
2. Compare original complete-results and start/scratch source contemporaneity; decide original provider's authoritative semantics for `place=0`, `kmTime=0,0`, scratches and non-start refund.
3. Only after independent provider contract review, prepare a separate isolated complete-results settlement test. No change to `nightly.py`/writer, no historical paper -25 NOK without separate HQ approval.
4. All original source/provider/private raw bodies stay off GitHub artifacts. No new schedule, Champion, autopromotion, BET or real-money authority.

Track [P0 settlement #82](https://github.com/Maremoo2/Betting/issues/82).
