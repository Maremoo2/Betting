# CORE-004 research candidate – conservative source-clock safety (30.10.2026)

**Bug class:** A candidate can be labeled `CANDIDATE_READY_UNCALIBRATED` from `races.start_time_utc - 4 minutes` even when an earlier, original archived independent provider source clock means the requested `as_of` is *after* the actual research T−4 bound. This is model-input retrospective leakage risk; it does **not** change Champion or real-money betting.

## Grounded case
[CORE-003 pilot 41120778717](https://github.com/Maremoo2/Betting/actions/runs/41120778717), pinned isolated SQLite `core003-pilot.sqlite` **0682fc437ae6f2d4470941ca28733eb1d8728031560a2e9ac5b48b07dd8b3249**:
- Romme race 8, canonical start **20:25Z**, archived ATG source-stated start **19:56Z** (difference **1740s**).
- Archived full-field fundamental features observed **19:49:19Z**; WIN market observed **20:07:53Z** (no betting should use it as pre-start).
- CORE-004 full-day as-of would be **20:21Z** based only on canonical start. An independently retained earlier source clock implies conservative T−4 **19:52Z**, so this **must be BLOCKED**.

## Restricted implementation and acceptance

- Only `src/hbi/core_multifactor_research.py`, synthetic guard tests and a read-only pinned archive workflow. **No** changes to candidate coefficients, scores, fundamental probabilities, Champion/V3.3.12, production decisions, staking, approval gates or data writers.
- Reuse CORE-003 **earliest archived source clock**, never a later revision. If an originally observed ATG source clock is malformed, mark research candidate BLOCKED. Output both original/earlier clocks and difference.
- Archived source cannot independently attest *actual off-time* or publication timestamp. Even a candidate evaluated before this conservative bound has `roster_point_in_time_attested=false` and no BET/EV permission.
- Real [pinned CORE-004 archive CI](../.github/workflows/core004-source-clock-gate.yml) must prove `ASOF_AFTER_EARLIEST_SOURCE_T4` and `status=BLOCKED` for Romme race 8 at formerly canonical T−4.
- Downstream CORE-004 training and P1 OOS remain blocked until immutable source publication/roster/clock original evidence [#83](https://github.com/Maremoo2/Betting/issues/83) and [#90](https://github.com/Maremoo2/Betting/issues/90).

**No future source backfill and no automatic BET or promotion.**
