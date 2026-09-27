# Horse Betting Intelligence — V3.2 architecture

## Principle

Benter defines the betting logic. Modern ML/AI is used to improve data discipline,
feature extraction, model validation and automation; it does not replace the
fundamental/public-market separation.

## Decision pipeline

1. **Point-in-time canonical data**
   - every feature must have an as-of timestamp
   - every source must have a publication timestamp
   - future information is a hard failure

2. **Market-free fundamental model**
   - no odds, tote percentages, exchange price or tipster rank
   - produces a full-field probability distribution summing to 1

3. **Race-difficulty / reject-option layer**
   - separate race-level diagnostic
   - never mechanically changes horse probabilities
   - can increase minimum edge, reduce stake, widen systems, or force PASS

4. **Static market model**
   - converts one coherent market snapshot to normalized full-field probabilities

5. **Market-path model**
   - T-30/T-15/T-10/T-5/T-2/T-1/close are separate time states
   - snapshots are stored as data, not overwritten
   - late movement is evidence, never automatically “smart money”

6. **Model-market conflict layer**
   - disagreement is not value by itself
   - unresolved disagreement increases shrinkage/uncertainty

7. **Combined probability**
   - Benter-style second-stage combination
   - coefficients must be estimated out-of-sample
   - production code must not hard-code unvalidated weights

8. **Price / EV / execution**
   - decision price, expected close, actual close and settlement are distinct
   - real-money auto-execution is deliberately out of scope

9. **Outcome / calibration**
   - frozen pre-race predictions are never rewritten
   - evaluate Brier, log loss, calibration, market-relative information and P&L

## Champion / challenger

Only the Champion influences production decisions. Challengers run in shadow.
Promotion requires an untouched sample and improvement on predictive calibration
metrics; economic metrics are reviewed separately.

## LLM role

An LLM may act as an evidence compiler:

unstructured source -> structured claim + provenance + confidence

It must not directly generate production p(win).

## Current implementation status

Implemented:
- point-in-time validator
- market-free probability primitives
- Benter-style probability combination primitive
- race-difficulty diagnostic
- market-path metrics
- calibration/evaluation primitives
- champion/challenger registry primitive
- normalized database schema
- CI tests

Intentionally not yet implemented:
- external race/market data ingestion
- learned model training
- closing-price model
- automated feature extraction from LLMs
- scheduled live market collection
- real-money execution
