# MODEL-003 Challenger V3 — SHADOW_ONLY, unfitted

Research code `hbi.model003_shadow_research` checks feature eligibility for five source-backed pre-target starts, verified identity and PIT status. It does not fit weights or activate a model.

BENCHMARK-002 V2 baseline (not rerun in this PR): F0 smoothed career winning frequency, F1 clean kilometre-time relative advantage/recency + layoff, F2 prior winner-payout class proxy (not official class), F3 day-delayed sequential opponent rating. New features require verified complete results/UELN before an actual V3 experiment. Existing retrospective 5,274 race V2+terminal WIN LL 1.5516082 vs calibrated terminal WIN 1.5569939 is NOT a decision-time PIT or EV result.

No 2022-24 raw cohort was supplied for independent reproduction here. All source+PIT gates yield 0 qualified V3 training rows in the DATA-007 cohort. V3 class/rating/LightGBM/market-combination experiments are NOT_TESTABLE and were not trained. Synthetic unit tests are only software fixtures.

Run `python -m pytest -q tests/test_model003_shadow_research.py`.
