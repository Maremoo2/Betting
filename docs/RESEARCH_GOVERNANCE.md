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

## Strategic kernel and evidence-driven next step

HBI uses Richard Rumelt's *Good Strategy/Bad Strategy* as a
**strategic-governance source**, not as horse-racing probability or wagering evidence.
William Benter remains the primary betting-methodology source.

The command/concept **build next step** is therefore not a calendar instruction. Before
new work is selected, HBI must state one current strategy kernel:

1. **Diagnosis** — what is the strongest evidenced obstacle to progress?
2. **Guiding policy** — how will HBI attack that obstacle without weakening existing
   research controls?
3. **Proximate objective** — what is the nearest measurable problem that can actually
   be solved now?
4. **Coherent actions** — what small set of changes jointly attacks that objective?
5. **Defer** — what attractive work is explicitly *not* being done yet?
6. **Empirical test** — what evidence will show that the bottleneck was resolved?
7. **Re-diagnose** — after the test, select the next weakest critical link from new
   evidence.

The machine-readable implementation is `hbi.strategic_governance`. The V1 system audit
emits `strategic_focus` on every run. A hard P0 failure outranks roadmap expansion. When
integrity passes, prospective evidence accumulation outranks unnecessary model
complexity. A date or roadmap phase cannot certify that the next phase is ready.

### Chain-link rule

HBI is treated as a chain-link system:

```text
identity -> PIT data -> full-field fundamentals -> probabilities -> market
-> combination/value -> executable price -> settlement -> evaluation
```

Improving a non-binding link must not be presented as strategic progress while a harder
critical bottleneck remains open. Fail-closed behavior is preferred to manufacturing
coverage.

### Create/destroy rule for research hypotheses

A Challenger idea must be falsifiable before registration. At minimum it needs a
diagnosis, mechanism, expected observation, explicit falsifier, candidate change,
confounders, discovery cutoff and untouched OOS plan. `validate_hypothesis()` enforces
that the idea is `CHALLENGER_ONLY` and has no production authority.

Discovery evidence may be used to create and try to destroy the hypothesis. It may not
also serve as the final promotion sample. Mid-sample redesign resets the research
question rather than inheriting the old forward evidence.

### Authority boundary

Rumelt-derived governance has **zero authority** to change p(win), model weights,
strategy thresholds, staking or execution. It determines what problem HBI should solve
next. Benter-first PIT/OOS/value governance determines whether a betting model is
actually supported.

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


## Scheduled intelligence boundary

Scheduled ChatGPT/pre-watch research is an evidence scout, not a strategy writer.

Qualitative findings enter HBI only through the append-only
`HBI_EVIDENCE_INBOX` staging worksheet and the validated
`intelligence_evidence` table. The bridge may preserve hypotheses and sourced
observations for later research, but Bridge v1 always stores them as:

- `research_only = 1`
- `production_feature_eligible = 0`

The scheduled intelligence layer cannot directly modify canonical market snapshots,
official outcomes, predictions, decisions, staking, settlement, Champion parameters
or promotion status. A qualitative signal can influence a future production model only
after normal point-in-time, out-of-sample and Champion/Challenger validation.
