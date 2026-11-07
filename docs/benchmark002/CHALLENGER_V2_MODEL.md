# Challenger V2

Status: SHADOW_ONLY, RESEARCH_RETROSPECTIVE. The implementation is an offline research command with no scheduler, database writer, policy integration, promotion or execution entry point.

## Architecture

Following William Benter's Computer Based Horse Race Handicapping and Wagering Systems, fit an independent fundamental full-field conditional logit. A separately fitted conditional logit combines log market probabilities with log fundamental probabilities. The Ventus paper on ensemble learning is secondary architectural context. This experiment separates forecasting and price/decision qualification.

Each field uses softmax of a common coefficient vector, minimizing mean race log loss with L2 penalty 0.03 in standardized feature space. Training precedes the calibration year, which precedes the test year. Test years are 2022–2024. Earlier outcomes can update horse state only after their whole date has been processed. Explicit timestamps for historical versions are missing. The date boundary prevents within-day lookahead in the retrospective replay but confers no PIT authority.

- F0 is the log of smoothed observed wins/starts using six prior starts at 1/N. F0 is fitted on the retrospective cohort. The frozen Champion used documented lifetime stats from its own data contract.
- F1 is mean within-prior-race clean kilometre-time advantage over the last five or ten observed starts, with shrinkage, plus days since last observed start. The exponential variant uses 90-day half-life. Observed archive history can omit starts. Missing observations contribute neutral values within this experiment.
- F2 uses the source-backed winner payout in older races as a noisy class proxy, plus interaction with prior time advantage. The exact source wrapper hash is checked. Unknown prize is omitted. The proxy has no currency or formal class normalization, and current race class is unavailable. No target result or prize enters its own feature row.
- F3 updates horse ratings from winner residuals under a race-wise softmax, with a fixed 0.15 step and one-day delay. It uses own rating and the mean prior opponents' rating over up to ten observed starts. This is an Elo-like experiment. It has no pedigree, direct meeting or provider-wide class claims.
- F4 and F5 are unmeasured. The adapter does not establish decision-time race conditions, age/breed, driver/trainer/equipment history or global identity. Explicit cold-blood/warm-blood separation and source-backed class effects require additional data. No gradient boosting was fitted.

The result is a full-field probability vector and a frozen coefficient report per fold. Fair odds for diagnostic use are reciprocals of the probabilities. The aggregate paired intervals describe the study estimates. No runner-level probability interval or verified live fair-odds contract is established.
`CHALLENGER_V2_0_SHADOW_SEASON_RESIDUAL_UNFITTED` from merged PR #172 is a distinct, frozen ATG career/season comparator. This benchmark adds an offline fitted historical experiment only. Its weights are never passed to that existing estimator or scoring workflow. The archive lacks the original ATG lifetime/current-season fields to score that comparator on the historical common cohort.
