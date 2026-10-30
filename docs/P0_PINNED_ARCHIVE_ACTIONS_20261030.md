# P0 | Pinned archived-state executable verification (30 October 2026)

This workflow runs the **already merged** `scripts/p0_archive_readonly_e2e.py` on an immutable, source-hash-checked real HBI snapshot. It does **not** run the main betting system, does **not** clear historical parity or settlement, and does **not** authorize any wager.

## Contract

- GitHub Actions workflow `.github/workflows/p0-archive-readonly-e2e.yml` runs on same-repository PRs touching the workflow or the archive CLI, or manual `workflow_dispatch`. **No scheduled execution or production runtime hook.**
- Source: [Watcher 41111189754](https://github.com/Maremoo2/Betting/actions/runs/41111189754), artifact `hbi-state`, internal artifact ID `13003343590`. Expected SQLite SHA-256: `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c` (531,005,440 bytes).
- Reference audit: [V1 system audit 41111521341](https://github.com/Maremoo2/Betting/actions/runs/41111521341), artifact `hbi-v1-system-audit-41111521341` ID `13002848843`, `research-v1/v1-system-audit.json` SHA-256 `fb5f9587e2a7e9bc09d04e66f17f5431d4d710aeb3562a2db7b85dac5233bfd6`.
- Both are independent source artefacts from **different capture times**. The workflow explicitly asserts a different decision denominator instead of disguising them as a single matching cohort.
- Python CLI reads database `mode=ro&immutable=1`, SHA-256 before and after. It writes only a JSON report outside the source paths. The **raw SQLite must never be uploaded** from this job.
- Workflow requires historical mismatches **exactly 5** with original and later-market source corroboration **5**, one still-open Shadow ticket without official settlement payload, and `p0_status=BLOCKED`, `real_money_authority=false`. Missing or altered artifacts must fail rather than fabricate a PASS.
- Report artifact contains only derived identifiers, evidence fingerprints and research diagnostics. It is **not** a rewritten outcome or source certificate.

## Scope distinctions

The new CLI measures **market-only** replay on available archived `market_probabilities_json`; the canonical V1 audit re-evaluates combined probabilities, conflict and decision status. Therefore their `checked` and `skipped` counts may differ even on the same state, and here the source snapshots themselves differ by one additional decision.

No new model weights, no market thresholds, no status overrides, no historical settlement or annotations, no strategy approval label, and no change to CODEOWNERS. Once verified on actual GitHub Actions, this closes only the *PINNED_ARCHIVE_DIAGNOSTIC_E2E* engineering submilestone, never P0 replay adjudication or P0 settlement.

Related [P0 replay #81](https://github.com/Maremoo2/Betting/issues/81), [P0 settlement #82](https://github.com/Maremoo2/Betting/issues/82), [CORE-003 PIT #83](https://github.com/Maremoo2/Betting/issues/83).
