# HQ-approved technical/historical CI separation — 27 November 2026

Applies only to PR #230's engineering review, never source/PIT/BET authority.
The exact 45 ZIP pins, 16 missing-original exceptions and nine historical groups
are frozen in `CI_APPROVED_SOURCE_LOSS_20261127.json`; its SHA is pinned in the
existing source verifier. Existing original SHA values and replay assertions stay.

`test` retains full Ruff/Pytest and all nine available-original replay groups.
`replay-v2-independent-readback` retains exact source/SQLite/ledger checks.
`historical-research-evidence` reports all nine historical groups, executes each
whose actual sources are available and remains FAILED/SOURCE_UNRECOVERABLE when
only the approved old originals are missing. It never calls a skipped replay PASS.

**`technical-acceptance` is the required aggregate for engineering review** in
addition to Research Integrity, Protected Strategy Files and NO/SE providers.
It requires both technical jobs to succeed, rejects absent/cancelled jobs, and
permits the failed historical job only when its verified summary proves exclusively
the exact HQ-approved source debt. Any available-original test regression, unexpected
skip, hash mismatch, changed pin set, retained-source loss or new gap blocks this
aggregate. The historical job remains visibly red, so this is not ALL_CI_PASS.

No repository rules/labels are modified. Owner review and approval of the exact
new HEAD remain required before merge; production needs separate authorization.
