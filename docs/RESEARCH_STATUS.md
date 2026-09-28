# HBI Effective Research Status

HBI separates **policy** from **current evidence**.

- `docs/research_governance.json` is the static governance/policy authority.
- `research-v1/research-status.json` is the automatically derived current evidence status.

This prevents a stale policy label from being mistaken for the result of the latest
real-state audit.

## Current evidence fields

The generated status records:

- V1 engineering status;
- operational and strategic validity;
- the frozen Shadow Champion and market baseline;
- effective P0 status for temporal integrity, provider integrity, runtime replay
  parity and settlement integrity;
- evidence counts such as checked rows/decisions;
- P1 status from governance;
- current learning-dataset size;
- Challenger forward clocks;
- immutable safety invariants: no execution authority, no auto-promotion and manual
  approval required.

## Meaning of P0 PASS

An effective P0 `PASS` means the latest restored-state audit found no integrity
failure in that control. It does **not** mean the betting strategy has an edge.

P0 can return to WARN / NO_EVIDENCE / FAIL on a later audit if provider, settlement,
temporal or replay evidence degrades.

## Strategic validity

Strategic validity remains a separately governed state. It cannot become VALIDATED
merely because all P0 controls currently pass.

The system still requires prospective evidence against the market-only baseline,
calibration, sufficient untouched sample size, and any Challenger's own forward
validation clock.
