# BET-001B3 — Prospective-only ledger recovery (draft)

This document is a local development plan, NOT permission to edit the canonical
Google Sheet or overwrite historical V3.3.12 records.

## Original evidence

Native Google Sheets `Betting V3.3 – Prospective Ledger`,
`PreWatchFunnel`:
- `U2` contains an ARRAYFORMULA extending through `U1500`.
- `U25` contains an explicit `IF(COUNT(P25:T25)=5,SUM(...))` formula.
- The real Sheets error in U2/V2/W2 says the array could not expand
  because it would overwrite `U25`.

The reported `#REF!` is a **process failure**, not `NO_EDGE`,
`BET`, or evidence that score thresholds should change.

## Dry-run and rollback

1. Export/copy the relevant source tab to a disposable, disconnected fixture.
   Record source row and file hashes, date and permission boundary.
2. Run `python -m pytest -q tests/test_prewatch_ledger_recovery.py`.
3. Use `hbi.prewatch_ledger_recovery.diagnose_row(row)` on a copy of each
   frozen row. Do not write the diagnostic status back as a historical decision.
4. Call `dry_run_future_formulas(rows,last_historical_row=N,first_future_row=N+1,last_future_row=M)`
   only on verified-empty future rows. It rejects historical and occupied rows.
5. Check output formula targets `PreWatchFunnel!U{row}`, each with exactly
   one row-scoped IF/COUNT/SUM formula, and verify existing U/V/W originals
   against their archived hashes.
6. **Rollback:** discard the plan/isolated spreadsheet. No remote change occurred.
   A production migration requires independent HQ authorization, protected
   change control, and an authorized backup/restore plan.

This module performs NO Sheets API reads/writes and is not imported by a
production writer. It cannot replace the original frozen A-WATCH gates.
