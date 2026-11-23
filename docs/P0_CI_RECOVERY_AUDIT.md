# P0 PR consolidation and authenticated CI artifact recovery audit — 2026-11-21

## Decision: do not rebaseline an immutable test by changing only the artifact reference

**PR #213 is the surviving integration PR.** Its source transport, frozen V3.3 gate and local Shadow logging are complemented with the explicit research-only Pre-Watch adapter + nine negative tests and design notes transferred unchanged from PR #212. No Champion, strategy or production change is authorized.

### Exact missing historical prerequisite

The failing `.github/workflows/ci.yml` original Collector-to-SQLite gate requests:
- Collector run `41399902762`, artifact `rikstoto-morning-programs`: **available** (artifact ID `13120034660`).
- Betting run `41518035718`, artifact `core003-pilot-state`: **not available** in GitHub Actions artifact inventory.
- Same Betting run, `bet-mvp-shadow-41518035718` and `core003-pilot-report-41518035718`: **available**.

The test `tests/test_collector_handoff_real_archive.py` independently pins original **2026-11-02** database SHA-256
`60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0`
and frozen model SHA-256
`dea4abdf8fed71c137274100153bfaec2323d608faec4072a569b4728cc789fe`.
Downloaded frozen model from the same historical run independently matches the model hash. The archived test additionally expects the 2 Nov original 3-race pre-import baseline to have **exactly three** Collector payload rows after new imports.

### Independently authenticated replacement examined

GitHub Actions Betting run `44907636310` (21 Nov 2026) publishes `core003-pilot-state`, artifact ID `14708117248`. It is a genuine GitHub Action output with a valid SQLite file named `core003-pilot.sqlite`.

- Downloaded Actions artifact ZIP SHA-256: `51e6cb4ee388d098b1cb3894f6133e293a30194ccb3d19ab41435c222881b699`.
- Raw database SHA-256: `c8d460aa6e50f5c7f63a976e70e572bd5cc7fc4148ee9bddef786dea2984b20d`.
- SQLite `PRAGMA quick_check`: `ok`.
- Contains each original 2 Nov race: `RIKSTOTO:OR_NR_2026-11-02:1` (7 runners), `:2` (9), `RIKSTOTO:S2_NR_2026-11-02:10` (8).
- But this is a **later cumulative state**, already containing **535 Collector original-roster payloads**. It is NOT byte-identical to the missing frozen 2 Nov snapshot.
- Its associated same-run model `race-002/shadow.json` is for `RIKSTOTO:S1_NR_2026-11-21:5`, not the expected `RIKSTOTO:S2_NR_2026-11-02:10`.

Therefore replacing the old run ID with `44907636310` and retaining the old test assertions **would fail**. Replacing only a SHA constant would be a dangerous false rebaseline: its database state, model run and expected import delta differ.

### Recovery choices

1. **Preferred:** restore the *exact* original 2 Nov `core003-pilot-state` artifact with expected raw SHA-256 `60dbb4...` to an authenticated GitHub Actions artifact in a suitable run, then update only the workflow's artifact reference with the preserved SHA checks, test logic and immutable model evidence untouched.
2. If the exact bytes are irretrievable, perform a separately reviewed **new authentic historical snapshot test**, preserving the old frozen test as a documented unavailable fixture, with new independent hashes, a source-state-aware baseline, and complete Collector→isolated SQLite→actual unchanged model + negative evidence. This is not an artifact-reference-only change, and requires explicit HQ scope approval before changing immutable test assumptions.

**This PR does not weaken or skip the original test, does not change the workflow, and cannot honestly be marked CI PASS.**

## Current acceptance

- SOURCE: verified subset only (four 21 Nov Jägersro original-byte SQLite readbacks in earlier audit). Historical frozen 2 Nov full E2E at exact PR HEAD: **BLOCKED**.
- SHADOW LIMITED: **NO-GO**; transport code is not a deployed Pre-Watch feed, original→v33 full-case/readback and 14-day parallel observation are missing.
- BETTING MODEL: **NO-GO**; independently attested runner identity, PIT, calibrated full-field probabilities, qualified WIN market and FFQ-1 cases are missing.
- Test paths changed in this PR carry source/transport negatives, not simulated gambling proof.
- Rollback: close PR #213; production main and Champion remain unaffected.

No merge or production decision is implied by source-readback PASS.
