# HBI Research Governance v1

The machine-readable authority for current research status is
`docs/research_governance.json`. This document explains the same rules for humans.

## Current separation

HBI distinguishes two independent questions:

- **Operational validity**: does the read-only/shadow system run, collect data, freeze
  decisions, settle outcomes and produce reproducible artifacts?
- **Strategic validity**: has a model demonstrated enough clean prospective evidence
  to justify promotion or higher-stakes use?

A green GitHub workflow is operational evidence. It is not proof of betting edge.

Current status is deliberately conservative:

- operational validity: `SHADOW_OPERATIONAL`
- strategic validity: `NOT_VALIDATED`
- automatic promotion: disabled
- adaptive switching: disabled
- real-money execution: disabled
- manual approval: required

## P0 research-integrity gates

No strategy-validation claim or promotion review can clear while a P0 gate is not PASS.

### Temporal integrity

All inputs must be available at or before the frozen decision timestamp.
HBI tests both stored timestamp order and a synthetic future-mutation invariance case.

### Provider integrity

Provider contracts, field coverage and source provenance must remain observable.
Missing provider data is a reason to degrade or stop a shadow decision, not a reason
to manufacture values.

### Settlement integrity

Official outcomes, shadow ticket settlement, P/L and CLV must reconcile. Contradictory
settlement is a hard research failure.

### Runtime replay parity

A frozen decision with complete provenance must replay through the same runtime
probability/value code and reproduce its combined probabilities, conflict score and
BET/PASS outcome.

This is the V1 precursor to full historical-backtest/runtime parity. Any future
historical backtest engine must reuse the same canonical feature/model/decision
components rather than implement a parallel strategy.

## P1 validation gates

P1 is downstream of P0.

- statistical validation
- challenger-specific forward validation
- eventual real-money readiness

A new challenger receives its own forward clock starting no earlier than its
registration/discovery cutoff. Historical races used to discover the idea do not count
toward its untouched prospective sample.

## Promotion authority

The system may calculate a recommendation-only readiness assessment. It cannot promote
a challenger automatically.

A future challenger must, at minimum:

- complete its required forward sample;
- beat the current Champion on log loss and Brier;
- beat the market-only baseline on the same clean sample;
- avoid material calibration deterioration;
- replicate across pre-registered race/market slices;
- pass all current P0 gates.

P/L and CLV remain secondary economic evidence and cannot replace probability scoring.

## Generated status safety

Automation may update research evidence and reports. It must not silently modify:

- the frozen Champion formula;
- strategy thresholds;
- probability-combination weights;
- staking rules;
- provider execution authority;
- promotion status.

Strategy-code protection is enforced separately in GitHub CI.
