# HBI research protocol

## Core benchmark

Every predictive model is evaluated against the **market-only baseline** on the
same races and the same point-in-time information set.

Primary predictive metrics:

- multiclass log loss
- multiclass Brier score
- calibration by probability band

Hit rate is descriptive only and must not be used alone to promote a model.

## Chronology

Training, tuning and evaluation must respect race time. Random train/test splits
are prohibited for production claims.

A candidate feature may only use information whose source publication time and
feature as-of time are no later than the decision time.

## Champion / challenger

The future production Champion is frozen once promoted. Until a calibrated model has
earned that status, HBI may designate one `SHADOW_CHAMPION` to drive prospective
paper decisions. Challengers remain shadow-only and cannot silently replace it.

A Challenger may be promoted only after:

1. point-in-time validation passes;
2. it beats the relevant prior Champion on an untouched chronological window;
3. it is compared against the market-only baseline;
4. calibration does not deteriorate materially;
5. any betting result is based on executable prices, not post-race reconstructed
   or optimistic prices;
6. the result replicates beyond the discovery sample.

## Betting layer

Prediction and wagering are separate layers.

The model first estimates p(win). The betting layer then receives:

- calibrated combined probability
- executable price
- race difficulty / reject status
- model-market conflict state
- total exposure constraints

A positive nominal EV can still become WATCH or PASS.

## Closing line

For each decision, preserve:

- available price at decision time
- expected closing price if a closing-price model exists
- actual closing price
- settlement/payout

CLV is an evaluation feature, not proof of profit.

## AI / LLM policy

LLMs can extract structured evidence and assist research. They do not directly
set production p(win). Multiple LLM opinions are not averaged into a probability
unless a supervised meta-model later proves incremental out-of-sample value.
