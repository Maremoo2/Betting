# INTEGRATION-001 — shared contract and CI/PR audit

Research branch. No production or betting changes.

Checked base: Betting main 7d5c80e02b521fbbaf5b76917952a8187df03fae, Collector main 0d860759e8065f50e9fd9f3371fa22438cfca1fc.
PR #173 and #175: merged. Collector PR #57: merged.
PR #176: open draft at 11762748b41209ade690b6600a85fecd27f305e2 (documentary only).
PR #177: open draft at cb77d8127afa49ff2e6399fecdcf09509213dd49 (official retrospective crosswalk; no PIT).

On PR #177 HEAD: CI run 42506003628 PASS; research integrity run 42506003658 PASS; protected strategy files 42506003623 PASS. Provider Live Smoke run 42506003667 FAIL, source reason NO_FULL_FIELD_LIVE_PASS:DK. The smoke failure is not the isolated historical CI failure, and is not green operationally.

Ownership: D docs/INTEGRATION_001* and common contract; A data009_*; B model003_*; C benchmark003_*. No protected strategy paths changed. Review D contract first, A and C independently after; B model only when source eligibility is settled; PRs #176/#177 stay draft until explicit review. All merges require a separate owner approval on exact HEAD.
