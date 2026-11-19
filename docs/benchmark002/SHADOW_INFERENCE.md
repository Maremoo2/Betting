# Manual V2 inference — partial, source-gated research

`hbi.benchmark002_shadow` reuses the original BENCHMARK-002 feature function,
softmax, market normalization, log-pool combination, value policy and exclusive
freeze writer. It neither fits a new model nor changes a runtime strategy.

The original 5,274-race benchmark was reproduced byte-for-byte from the preserved
inputs on base `f9cfbd1403ab392d89808d9eea4534b331696b29`. Its terminal-market
combination LL is 1.551608198995003, versus 1.556993940786104 for the fixed
calibrated terminal market. This is exposed retrospective evidence, not a live
probability, executable-price or economic validation.

The latest documented artifact uses the original 2024 fold: fundamental training
through 2022, combination calibration in 2023. Its coefficients and feature order
must be pinned to a SHA-verified artifact. The separate ATG career/season estimator
is a different model and does not receive these weights.

## Two manual phases

```text
python -m hbi.benchmark002_shadow fundamental --artifact MODEL --artifact-sha256 SHA
  --input SOURCE_BOUND_STATE_PACKET --input-sha256 SHA --output NEW_FUNDAMENTAL_FREEZE

python -m hbi.benchmark002_shadow combine --artifact MODEL --artifact-sha256 SHA
  --input ORIGINAL_WIN_ENVELOPE --input-sha256 SHA
  --fundamental-freeze FREEZE --freeze-sha256 SHA --output NEW_SHADOW_DECISION
```

Join each command onto one line in a shell. These entry points use actual UTC
processing clocks and never overwrite existing output. Library clock arguments
are solely for controlled tests and explicit retrospective replay.

The historical demonstration binds Bjerke 2024-01-02 race 1 to original native
registrations and 621 previously observed horse starts. Fundamental and combined
probabilities match the original benchmark within 1e-16. All seven active runners
receive SHADOW_PASS. Historical prices remain non-executable retrospective data.

## Live boundary

PROSPECTIVE mode is deliberately blocked until a reviewed source-bound V2 live
state adapter exists. A caller-created numeric state or a successful asserted
canonical row cannot bypass that boundary. The existing historical dataset gate
requires outcome labels and is not repurposed as a live inference gate.

A real Bergen race 1 candidate on 2026-11-19 was captured and tested before its
18:51 Europe/Oslo cutoff. The original program and startlist identify eight listed
horses, seven active. The 35 active-horse form-row candidates are insufficient for
the complete prior-field relative times, historical winner-purse series and
day-delayed opponent graph. Independent permanent identity/scratching evidence
also remains unqualified. No live prediction or WIN request was issued.

Complete artifacts and source receipts are preserved in the local P1-014 output.
There is no scheduler, database writer, stake, BET authority, automatic promotion,
deployment or production adoption in this module. Terminal-price calibration
cannot be transferred to T−4 prices by assertion.
