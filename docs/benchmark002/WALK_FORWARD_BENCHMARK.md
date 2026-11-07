# Walk-forward benchmark

This is a retrospective experiment on already inspected 2015–2024 material. The 2022, 2023 and 2024 test years use an expanding training prefix and the immediately preceding year for the market-combination fit. All models are scored on an identical physical race and selection-number set with a matching winner. Selection matching uses the same source namespace. Permanent cross-provider identity remains unproven. Legacy and WIN vectors come from the original archived terminal-price research.

Reference values reproduced by BENCHMARK-001: LegacyCombined LL 1.60367684, calibrated terminal WIN 1.60614252, normalized terminal WIN 1.61328234, on 15,221 races. LegacyCombined paired delta −0.002466, week CI [−0.003462, −0.001512]. First30 LL WIN 1.94910626, CORE-004 2.08769489, Champion 2.12908725, uniform 2.28654808. Existing 2,423-race development ablations found +0.06360 without historical performance, +0.02089 without recency, +0.01197 without opponent correction.

Champion and CORE-004 have no comparable 2015–2024 frozen predictions in the preserved inputs. They remain NOT_TESTABLE on this common cohort. F0 is an explicitly fitted observed-career baseline. It cannot replace their reported metrics. Normalized WIN, fixed calibrated WIN and LegacyCombined are measured at the terminal archive. PIT-certified and economic rankings remain NOT_TESTABLE.

## Reproduce

From the research branch with Python 3.11 and NumPy installed, use the local project root holding the unmodified frozen inputs. Set OPENBLAS_NUM_THREADS to 1 for replay and select a new empty output path.

```
python -m hbi.benchmark002_retrospective PROJECT_ROOT NEW_OUTPUT
python -m hbi.benchmark002_summary NEW_OUTPUT
```

The first command produces full-field predictions and the fold/source report. The second produces paired 95% week bootstrap intervals, calibration, favorite diagnostics, and ABLATION_RESULTS.csv with Holm adjustment across the tested contrasts. Negative delta favors the first model. These uncertainty estimates condition on the chosen study design and exposed archive. Future untouched shadow evidence is needed for generalization.

CHAMPION_UNCHANGED=true
PREWATCH_V3_3_12_FROZEN=true
CHALLENGER_SHADOW_ONLY=true
NO_LOOKAHEAD=REQUIRED
2025_LOCKBOX_CLOSED=true
PIT_HARDGATES_UNCHANGED=true
AUTO_BET=false
BET_AUTHORITY=false
AUTO_MERGE=false

## New results on the common retrospective cohort

| Candidate | Log loss | Brier | ECE 0.10 | Status vs calibrated terminal WIN |
| --- | ---: | ---: | ---: | --- |
| Challenger V2 + market | 1.5516082 | 0.6929415 | 0.0047427 | SUPERIOR on this retrospective LL contrast |
| LegacyCombined | 1.5545104 | 0.6933397 | 0.0040920 | SUPERIOR on this retrospective LL contrast |
| Calibrated terminal WIN | 1.5569939 | 0.6937543 | 0.0039238 | Reference |
| Normalized terminal WIN | 1.5652601 | 0.6966418 | 0.0107086 | INFERIOR |
| Challenger V2 fundamental | 1.8247338 | 0.7846381 | 0.0075126 | INFERIOR |
| Simple recent form | 1.8451295 | 0.7912964 | 0.0105001 | INFERIOR |
| Uniform | 2.1878630 | 0.8840020 | 0 | INFERIOR |
| Frozen Champion and CORE-004 | — | — | — | NOT_TESTABLE on the common cohort |

All measured rows use 5,274 races and 158 week blocks. Paired sample sizes are 1,837 in 2022, 1,749 in 2023 and 1,688 in 2024. Before matching to the archived market and Legacy fields the test folds contain 8,526 eligible full fields. For Challenger + market, delta LL vs calibrated terminal WIN is −0.005386 with 95% week interval [−0.008902, −0.001974]. Paired delta Brier is −0.000813 with interval [−0.002396, +0.000749]. The exploratory comparison against LegacyCombined is −0.002902 LL, interval [−0.005800, −0.000031], without a multiplicity correction on this secondary head-to-head. Generalization against decision-time WIN remains NOT_TESTABLE.

Adding F1 reduced LL by 0.084970 compared with the fitted career baseline. F2's winner-payout proxy increased LL by 0.001684. F3 reduced LL by 0.022080 against form plus the same proxy. These are within-experiment estimates, not estimates of the effect of verified class or certified history.
