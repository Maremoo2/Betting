# CORE-003 | Earlier source clock must constrain T−4 readiness (30 October 2026)

**Incident class:** A source-only prospective Shadow pilot may count complete input when the mutable canonical scheduled start is later than an archived source-stated scheduled start. This is a research-data measurement defect, **not** a bet execution or live-model override.

## Primary case: Romme, Sweden, 2026-10-30, race 8

[CORE-003 pilot run #41120778717](https://github.com/Maremoo2/Betting/actions/runs/41120778717), original state artifact **13008497207**, report artifact **13008097779**. Original `core003-pilot.sqlite` SHA-256: `0682fc437ae6f2d4470941ca28733eb1d8728031560a2e9ac5b48b07dd8b3249` (8,273,920 bytes).

| Source | Observed / source UTC |
| --- | --- |
| `races.start_time_utc` | **20:25:00** |
| ATG full-field source-stated `race_start_utc` | **19:56:00** |
| `runner_fundamental_snapshots` (8/8 active) | **19:49:19.037433** |
| `provider_market_snapshots` (8 WIN selections) | **20:07:53.009214** |

The two archived clock values differ **29 minutes**. Canonical T−4 is **20:21**; conservatively using the earlier source-stated start makes T−4 **19:52**. Therefore the WIN odds snapshot is **after even the source-stated start** and must not count toward pre-race readiness.

The earlier pilot report had `races_full_sources=1/6` based on the later canonical clock. **This is invalid as conservative source-time readiness and was never PIT certified** (`roster_pit_verified=false`, `source_published_at_utc=null`).

## Scoped correction in this PR

- Change only **unprotected research-only** `src/hbi/core_shadow_pilot.py`; no `src/hbi/provider_capability.py`, production policy, Champion, model, external scheduler, betting/stake or state write change.
- Recover all archived ATG full-field source-stated starts in the exact race prior to the old canonical cutoff; use the **earliest valid clock** as a conservative upper bound for T−4 counting. Continue reporting the canonical clock and explicit conflict seconds. A malformed recorded source clock invalidates the provisional full-source status.
- Never claim actual off-time, provider publication timestamp or PIT certification from these fields. A missing source-stated clock remains unverified and can be marked provisional raw readiness under old source/roster caveat; it is **not** an automatic positive PIT result.
- Add three negative regression tests: market after earlier start is not ready, later revised source time cannot reopen the earlier cutoff, corrupt source clock blocks readiness.

## Acceptance

1. Full repository CI, Ruff, protected files and clean research integrity pass.
2. Re-run on archived actual [pilot state 13008497207](https://github.com/Maremoo2/Betting/actions/runs/41120778717) with the fixed metric, read-only, preserve archive SHA; expected **0/6** conservative complete input fields (historical one was post-source-time market).
3. Keep `roster_pit_verified=false` until original publication and immutable revisions are attested.
4. Independent approval before merge. Any existing historical Shadow metrics are source observations, not approval to rewrite frozen decisions.

Related: [CORE-003 issue #83](https://github.com/Maremoo2/Betting/issues/83), [P0 replay #81](https://github.com/Maremoo2/Betting/issues/81). **Real-money OFF.**
