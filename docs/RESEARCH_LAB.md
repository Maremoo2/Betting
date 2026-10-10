# HBI Research Lab v1

Run alongside collection in a separate worktree. This module has no crawler, decision,
staking, settlement or promotion writes. Champion and frozen PRE-WINNER rules remain unchanged.

## Registries

`research/registry.json` contains hypothesis, source and academic-position registries.
The six initial hypotheses are proposals, not completed preregistrations. Unknown papers,
bibliography and evidential strengths must be reviewed against original sources; no
peer-review, sample-size or PIT-quality claims have been invented. Link source IDs only
after review. Position changes require a dated reason and evidence in revision_history.

## Data roles and exposure

2015–2022 development; 2023 internal validation; 2024 late challenger validation.
2025 is only a lockbox candidate: pilot outcomes and automatically generated scoring
already exist. Audit exposure and identify unopened subsets before enabling access.
2026 January–September has already been analysed and is not untouched future OOS.
Future OOS requires a new frozen registration before opening its outcomes.

## Experiment contract

Provide a JSON plan with experiment_id, hypothesis_id, git_commit, features, model,
hyperparameters, dataset_sha256 (canonical JSON digest from hbi.research_lab.digest),
primary_metrics, exclusions, slices, train_period, test_period, data_cutoff, test_role.
All dates require timezones. Training is restricted to development years. The module
records immutable plan and registry hashes. Historical registration is explicitly not
prospective preregistration. Do not relabel previously examined hypotheses as blind tests.

```powershell
python -m hbi.research_lab register --input plan.json --output runs/experiment/registration.json
python -m hbi.research_lab evaluate --input runs/experiment/registration.json --dataset dataset.json --output runs/experiment/result.json
```

The dataset is a JSON list of races. Each race requires race_id, start_at,
active_runner_ids, winner_id, result_complete=true, identity_verified=true,
market_snapshot_type=PRE_RACE_VERIFIED, market_available_at, and runners.
Each runner requires runner_id, identity_verified=true, prediction_at,
model_probability, market_probability, and features keyed by registered feature name.
Each feature requires value, event_at, available_at and source_sha256.
Probabilities are externally generated research distributions, never HBI scores converted
implicitly into betting probabilities. No fitting or hyperparameter search occurs here.

Every active runner must match once. Both feature event and availability timestamps,
predictions and market availability must precede start. Entire normalized distributions
are checked. Incomplete results, dead heats, terminal unverified prices and missing fields
are recorded as exclusions; duplicates abort evaluation. A hash mismatch aborts evaluation.
Outputs include paired log-loss differences, multiclass Brier, calibration bins and
registered slices on identical accepted races. These are diagnostics, not significance
or promotion evidence. Combined models may be evaluated as separate registered experiments;
the harness does not automatically train, combine or select models.

## Current readiness

The archive provides market distributions and some identity-verified outcomes. It does
not yet establish historical pre-start market availability, full sports-history fields,
km times, equipment, gallop/DQ, or stable historical opponent features. Therefore the
strict PIT harness can legitimately return BLOCKED_NO_PIT_DATA for archive inputs.
Do not fabricate timestamps or map a migration timestamp to race time.

Synthetic smoke tests verify the harness without opening historical lockbox outcomes.
Next: audit development-only field coverage, then construct a documented adapter for
fields actually present. Historical terminal-market scoring must be labelled separately
from PIT or executable prediction. Economic simulation remains NOT_ESTABLISHED until
verified prices, payouts and execution assumptions have their own frozen protocol.
