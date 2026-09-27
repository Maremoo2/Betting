# Fundamental Shadow Champion v1

## Purpose

`FUNDAMENTAL_CHAMPION_V1` is the first autonomous **market-free** horse-level
probability model in HBI. It exists to make the shadow loop end-to-end and to create a
clean prospective dataset for later model research.

It is deliberately simple. It is **not** claimed to be calibrated, profitable, or
better than the tote market. It is registered as `SHADOW_CHAMPION`, not the validated
production `CHAMPION`.

## Data contract

The model reads only the base Rikstoto program payload captured before the decision.
The provider's historical frontend contract exposes runner facts such as:

- start number / post position
- horse, driver and trainer
- age / sex
- extra distance
- total earnings
- auto / volt records
- horse annual statistics, including starts and first/second/third places

The current v1 probability formula intentionally uses only:

- total historical starts
- total historical first places

Other captured fundamentals are stored for future challengers but do not influence v1.

The model never receives:

- win odds
- place odds
- V-game investment percentages
- pool totals
- exchange prices
- tipster/expert ranks
- post-race outcomes

The collector therefore uses `/api/game/program/{raceday}/{product}` and not
`program/addition` for fundamental features.

## Formula

For an active field of size `N`, the neutral prior win probability for each runner is:

`prior = 1 / N`

For runner `i` with `wins_i` wins from `starts_i` historical starts:

`strength_i = (wins_i + K * prior) / (starts_i + K)`

where v1 pre-registers:

`K = 6 prior starts`

The strengths are then normalized across the full active field so that:

`sum(p_i) = 1`

This is an empirical-Bayes shrinkage baseline. A lightly raced horse is pulled toward
the neutral field prior; a horse with more historical starts is influenced more by its
observed win record.

A runner with genuinely known zero starts is valid data. A runner whose historical
statistics are missing receives the neutral prior before field normalization.

## Point-in-time rules

Every fundamental snapshot stores both:

- provider observation timestamp
- `feature_as_of_utc`

Before a prediction is created, HBI verifies that no feature timestamp is after the
decision timestamp.

Predictions are frozen. The model cannot rewrite a T-4 prediction after the result.

## Shadow eligibility gate

The model can generate a complete probability vector even when some runner history is
missing, but the betting layer may not use every such vector.

Default v1 gate:

- at least 2 active runners
- historical start/win statistics known for at least 80% of active runners

Below that threshold the run is stored as `CAUTION / LOW_HISTORY_COVERAGE` and the
shadow layer records `NOT_EXECUTABLE` instead of manufacturing a paper bet.

## Why this is intentionally small

Benter's architecture requires an independent fundamental estimate before the public
market is combined with it. It does not imply that every available feature should be
added immediately.

The 2026 evidence reviewed for this project also supports aggressive leakage control,
feature ablation and simple baselines before larger ensembles.

So v1 does **not** yet weight driver, trainer, earnings, record time, post position,
current-year form, pedigree or race conditions. Those are stored as candidate feature
blocks for chronological challenger tests.

## Promotion path

The shadow Champion should be replaced only after a challenger is tested on frozen,
chronological data.

Required evaluation includes:

1. multiclass log loss;
2. multiclass Brier score;
3. probability calibration;
4. comparison with this v1 baseline;
5. comparison with the market-only baseline;
6. executable-price betting results and CLV as separate economic diagnostics.

No profitable discovery backtest is enough to promote a model by itself.
