# Horse Betting Intelligence — V1 system architecture

## Principle

V1 is the system/platform milestone. The underlying betting methodology remains the
Benter-first V3.2 decision architecture developed for this project.

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
   - late movement is evidence, never automatically "smart money"
   - material changes trigger a fresh pre-watch reprice/review rather than a bet

6. **Model-market conflict layer**
   - disagreement is not value by itself
   - store model-vs-market residuals as candidate features/diagnostics
   - unresolved disagreement increases shrinkage/uncertainty

7. **Combined probability**
   - Benter-style second-stage combination
   - coefficients must be estimated out-of-sample
   - production code must not hard-code unvalidated weights

8. **Price / EV / execution**
   - decision price, expected close, actual close and settlement are distinct
   - log closing-line value for research; never rewrite the original decision
   - real-money auto-execution is deliberately out of scope

9. **Outcome / calibration**
   - frozen pre-race predictions are never rewritten
   - evaluate Brier, log loss, calibration, market-relative information and P&L

## 2026 AI lessons adopted

The useful lesson from current AI products is architecture, not marketing claims:

- real-time feeds and last-minute changes matter, so pre-watch must be event driven
  as well as time scheduled;
- independent models may contribute probabilities or structured features, but
  naive LLM majority/consensus voting is not a probability model;
- unstructured observations such as trip trouble, equipment/driver/jockey changes,
  scratches, weather and track changes belong in a provenance-preserving review
  queue until a validated feature pipeline exists;
- data quality, leakage prevention and reproducibility outrank model novelty;
- AI confidence is not a staking signal.

Claims such as generic win-rate improvements, guaranteed ROI, or a system that
"learns after every race" are not accepted without point-in-time out-of-sample
evidence.

## Champion / challenger

Only a validated `CHAMPION` may influence future production decisions. The current
autonomous paper loop uses a separately labelled `SHADOW_CHAMPION`; challengers also
run in shadow.
Promotion requires an untouched sample and improvement on predictive calibration
metrics; economic metrics are reviewed separately.

Candidate challengers can include tree/boosting models, neural models, market-path
models and structured LLM-derived features. They must all face the same walk-forward,
calibration and leakage tests.

## LLM role

An LLM may act as an evidence compiler:

unstructured source -> structured claim + provenance + confidence

It must not directly generate production p(win). Multiple LLMs may be used as
independent evidence extractors/research assistants, but their votes are not averaged
into a production probability unless a later supervised meta-model proves incremental
out-of-sample value.

## Pre-watch policy

The live layer compares each new timestamped snapshot with the prior state. Material
odds/probability movement, rapid pool growth, or a structured material event triggers
REPRICE or REVIEW. Operational thresholds are configuration candidates, not learned
truths, and must be calibrated on historical snapshots before production use.

A late shortening is never automatically labelled informed money. The model asks:
what changed, when did it change, was the pool sufficiently mature, did the move
persist, and did similar point-in-time patterns historically add information beyond
the market baseline?

## Current implementation status

Implemented:
- Research Observatory v1 for prospective data-health and model/market evaluation
- frozen T-4 decision audit covering BET, PASS and NOT_EXECUTABLE
- immutable nightly research backups with SQLite integrity verification and SHA-256
- read-only Rikstoto provider with explicit endpoint-provenance levels
- live-smoke-verified Rikstoto `/starts` canonical race-field snapshots
- Swedish ATG point-in-time market-free lifetime-history enrichment
- `FUNDAMENTAL_CHAMPION_V1_1` shadow Champion using historical win records
- full-field normalization and 80% history-coverage shadow eligibility gate
- five-minute market watcher with best-effort T-4 timing and latency logging
- immutable shadow ledger
- Vinner shadow execution when full-field fundamental probabilities exist
- official Vinner settlement, CLV and nightly paper P/L reporting
- V/P/TV/T market collection; dead historical program/pool endpoints removed from the live path
- point-in-time validator
- market-free probability primitives
- Benter-style probability combination primitive
- race-difficulty diagnostic
- market-path metrics
- material-change pre-watch trigger primitive
- structured human-review flags
- model-vs-market residual primitive
- decision/closing-price/CLV storage fields
- calibration/evaluation primitives
- champion/challenger registry primitive
- normalized database schema
- CI tests

Intentionally not yet implemented:
- calibrated/learned production Fundamental Champion
- verified Norwegian pre-race horse-history enrichment
- validated incremental feature blocks for driver/trainer/form/earnings/record/etc.
- validated current payout/dividend contracts for TV/T/DD/V4/V75/V85
- autonomous shadow probability/ticket models for P/TV/T/DD/V4/V75/V85
- learned champion model training
- learned closing-price model
- automated feature extraction from LLMs
- low-latency always-on collector (GitHub scheduling remains best-effort)
- real-money execution


## V1 control plane

The decision/data plane is intentionally separated from a read-only control and
learning plane:

- `docs/research_governance.json` is the machine-readable governance authority;
- `research_integrity.py` checks point-in-time ordering and future-mutation invariance;
- `replay_validation.py` replays frozen decisions through the same runtime code;
- `settlement_integrity.py` reconciles official outcomes, P/L and CLV;
- `learning.py` produces a deterministic research dataset from frozen records;
- `challenger.py` gives every Challenger a separate prospective validation clock;
- `promotion.py` can only emit a recommendation for manual review;
- `counterfactual.py` evaluates hypothetical policies without changing original
  decisions or execution authority;
- `manifest.py` hashes critical code, schema, policy/governance and run metadata.

This mirrors the strongest lesson from AI-Trader: operational validity and strategic
validity are separate states.
