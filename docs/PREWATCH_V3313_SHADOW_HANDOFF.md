# V3.3.13 Pre-Watch Shadow handoff (research-only, no BET)

This change contains a **source provenance fix** and a **fail-closed transport
adapter**, not a new probability model, WIN collector or operational Pre-Watch
activation.

## Roles and permissions
- `collector_handoff.verify_import()` continues to enforce physical original
  source SHA, full-field identity, and independent PIT/model admission gates.
- `hbi.prewatch_shadow_handoff.build_handoff()` only serializes a canonical
  Collector handoff into a non-executable source/model/market report.
- `betting.v33` remains the only V3.3 decision contract; this change **never
  invokes it without a verified full-field model, WIN odds, FFQ-1 case evidence
  and registered forward batch**.
- Pre-Watch V3.3.12 Champion is unchanged. A V3.3.13 feed must be activated
  separately with explicit HQ authorization. No workflows or schedules change.

## Delayed starts
A physical PDF start time can differ from a subsequently recorded scheduled
start. The importer keeps the physical original PDF identity and both observed
clock values. Where pre-decision revision observations exist in the isolated
database, it records `COLLECTOR_START_REVISION_REQUIRES_PIT_ATTESTATION` and
can preserve the original roster in SQLite. It **does not** attest actual off
time or lift the model/market/EV gates. Where no retained source observations
exist, the original `COLLECTOR_PDF_START_CLOCK_CONFLICT` remains. Older DB
fixtures lacking the schedule-observations table retain the original fail
closed behavior.

## Research-only transport
The adapter requires an already-verified source import receipt, stable
full-field membership and SHA-shaped provenance to report SOURCE_READY. It
does not independently rehash or certify source bytes; source receipts must
first come from the real Collector verifier. SOURCE_READY never implies
FUNDAMENTAL_READY or BET_READY. Model and market metadata provided to the
adapter are indications for future Betting v33 review, not betting evidence.
All outputs have `probabilities=null`, `expected_value=null`,
`bet_authorized=false`, `execution=SHADOW_ONLY`.

The `write_once_and_readback` function creates a **new** JSON file and
verifies exact byte readback. Existing files are never rewritten.

## Tests and remaining requirements
- Focused tests: `python -m pytest -q tests/test_prewatch_shadow_handoff_v3313.py`
- Full CI: `ruff check .` then `pytest -q` on this PR head.
- Existing original Collector ZIP provenance must be checked separately.
- Genuine historic cross-provider identity remains unverified for the reported
  Jägersro cohort; missing WIN odds, a calibrated fundamental probability
  and a complete v33 case audit remain independent blockers.
- This PR is NOT evidence of a successful end-to-end Betting V3.3 betting
  assessment, a prospective T-4 decision, or season-ready deployment.

## Activation / rollback
Separate HQ authorization is needed to merge and separately to activate any
read-only scheduled Shadow ingestion. Before activation: verify an authentic
full-field archive-to-Betting-runtime replay with explicit terminal status,
≥14 day parallel comparison, no Champion drift, append-only reports and
readback, error paging and rollback. Rollback: disable only the *separately
authorized* V3.3.13 transport and retain immutable archived reports.
