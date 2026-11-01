# V1 P0 – read-only original-state provenance and settlement forensics

## Scope
This work does **not** reclassify, delete or overwrite any failed \`runtime_replay_parity\` or \`settlement_integrity\` result. It never edits a frozen decision, original captured provider quote, official winner, paper ticket, stake, payoff, model parameter or source database.

The last available HBI V1 System Audit on 2026-11-01 reported **312 checked/5 failed** replay decisions, **477 skipped**, and **one** overdue open shadow ticket despite an \`outcomes\` winner. The existing \`legacy_provenance.classify_legacy_replay\` independently checks for original market snapshots at the exact frozen observation timestamp and separates a late-attached provenance anomaly from irreconcilable mismatches. Its result remains a *forensic explanation*, not permission to repair history or claim replay PASS.

## Reproducible command

Use a genuine checkpointed copy of the published HBI SQLite state, never the live writer file. Offline invocation:

\`\`\`bash
python -m hbi.v1_p0_triage --db /path/to/original-checkpointed-hbi.sqlite \
  --output v1-p0-readonly-triage.json
\`\`\`

GitHub Actions PR check \`V1 P0 Exact-State Forensics (Read Only, No Admission)\` restores the most recent real main-branch \`hbi-state\` artifact into a temporary workspace, runs a reproducible read-only legacy-provenance source comparison, and reports overdue shadow tickets with a separate stored winner. It hash-checks the source DB before and after and uploads ONLY the derived JSON and the source restoration result, never original provider data or SQLite.

### Evidence interpretation

- \`legacy_late_attachment_original_source_reconstructed\`: historical mismatches that can be *explained* by genuine exact-time archived market odds and late saved provenance. Existing immutable \`decision_provenance\` and shadow runs stay exactly as they are; V1 audit stays FAIL.
- \`historical_replay_unreconciled\`: mismatches not proved by original market replay. These are **hard** outstanding evidence failures.
- \`incomplete_provenance_skipped\`: no replay evidence; do not call them PASS.
- \`overdue_unsettled_with_stored_outcome\`: paper tickets for which an outcome winner was recorded, but ticket was not settled after 24 hours. This is NOT enough original official \`complete_results\` or final dividend evidence for any loss, win or refund. Inspect actual public original result and dividend status via existing conservative settlement evidence procedure, without assuming an amount or backdating the database.

Both \`original_v1_audit_overridden\` and \`model_or_bet_authority\` are explicitly false. The P0 is not resolved by a green **diagnostic** workflow. The exact original V1 System Audit still determines whether P0 PASS has been achieved.

### Do not do
Never manually set the recorded winner's payout from market odds, infer a losing ticket from \`place=0\`, infer a runner scratch/refund, reconstruct a new BET, or rewrite \`decision_provenance\` to make the historical V1 audit green. No main or scheduled-nightly workflow changes are in scope. An HQ-authorized source correction, if ever needed, must preserve old decisions and be separately reviewed.
