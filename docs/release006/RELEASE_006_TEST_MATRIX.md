# RELEASE-006 · Test matrix

Base `3dce8f98f312c67b8b6f7a5120283d24c9ba18e8`. The draft PR body records the exact delivery HEAD and status of GitHub checks.

| Check | Evidence |
| --- | --- |
| SQLite migration and restart | PASS on authentic archived copy. See SQLite integrity report for hashes and row counts. |
| Signal and PIT regressions | Targeted Pytest covers missing originals, wrong race/model/identity, conflicts, late or absent postcommit, invalid distribution, retry, SQL replacement/deletion and rollback. |
| KPI isolation | Targeted tests verify empty primary metrics and calibration with real legacy rows in the fixture, alongside separately readable legacy metrics. |
| Ruff | Changed Python files passed. The full Windows run with Ruff 0.16.9 found eight DTZ findings in unchanged files. |
| Full Pytest and GitHub CI | Exact delivery results are recorded in the draft PR. |
| Historical original replay | BLOCKED, HISTORICAL_ARTIFACT_UNAVAILABLE. Run 41518035718 artifact inventory returned only core003-pilot-report and bet-mvp-shadow. The required core003-pilot-state for expected SHA-256 `60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0` was absent. No substitute was replayed. |
| Live PIT acceptance | BLOCKED pending an independently witnessed source-to-model-to-commit result on real races. |
