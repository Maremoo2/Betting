# MVP-021 P0 isolated QA – duplicate official race start number must fail closed

**Date:** 2026-11-05 · **Code base:** `main=2238a9b891b16cd74ced7eaa581c630dd572f4b9` · **No real betting or settlement writes.**

## Reproduced implementation defect

In `src/hbi/nightly.py::_finish_map`, the prior implementation was `output[str(start)] = int(place)`. If the official `complete_results.results` contained two entries with the same `startNumber`, the last row silently overwrote the first. A contradictory duplicate `#3 place=1` then `#3 place=2` was silently reduced to `#3 place=2`. A `V` losing ticket could then be `SETTLED` if a different #6 winner had a positive published dividend. This violates the existing source-integrity requirement for a unique official selected runner and a stable full race result.

**Important provenance limit:** The duplicate rows used to reproduce this bug are deliberately **negative QA fixtures**, not a claim that any genuine Skive/Eskilstuna/Bjerke official original actually contained duplicate numbers. The genuine Eskilstuna `S1_NR_2026-11-03:7` selected `#3 place=0 kmTime="19,1"`, disqualified `#2 kmTime="Dsk"`, winner `#6`, are used only as *positive unchanged* semantics examples.

## Minimal safeguard

- While building the official finish map, record every non-null start number. On **any** duplicate, even if the second row is incomplete, return an empty map.
- The preexisting settlement gate already refuses `V` tickets when selected finish is missing; `P` also stays pending on empty map. Thus a duplicate triggers **pending/fail-closed** without introducing new settlement outcomes, inferred refunds, odds or risk changes.
- Existing unique-row `place>0`, numeric `place=0` and `Dsk` semantics remain exactly as before.
- Regression tests check duplicate selected horse, duplicate winner, contradictory selected rows, duplicate `Dsk`/missing finish, idempotent two-run paper-only pending behavior and exact unique-result unchanged functionality. All state writes happen **only to disposable temporary test SQLite**.

## Governance

No canonical SQLite, historic ticket, model, Champion/CORE004, V3.3.12, PIT/T−4, BET/WATCH/PASS, minimum odds, stake, autobet or automation changes. `bet_authority=false`. Draft PR only; owner merge approval is required. This safeguard does **not** settle [Skive #82](https://github.com/Maremoo2/Betting/issues/82), [Eskilstuna #144](https://github.com/Maremoo2/Betting/issues/144) or [Bjerke #149](https://github.com/Maremoo2/Betting/issues/149), because their missing source/contract interpretation remains separate.
