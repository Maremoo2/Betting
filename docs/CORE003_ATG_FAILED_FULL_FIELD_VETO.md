# CORE-003 P0 — Explicit third-party failed full field must veto source readiness

The isolated research pilot (not the production BET engine) independently
evaluates frozen fundamental snapshots and WIN market snapshots. Until this
change, a pre-T−4 \`provider_payloads\` ATG \`FULL_FIELD_ONLY_V1\` source
could explicitly report \`passed=false\` (or deficient runner identity)
while \`_readiness\` still returned \`history_complete_as_of_t4=true\`,
\`win_market_complete_as_of_t4=true\` and a **false-positive**
\`all_inputs_complete_as_of_t4=true\` from other snapshots.

## Changed research-only source contract

If *no eligible ATG full-field source observation exists*, the isolated
source-readiness measure continues to describe provisional completeness of
other provider snapshots; the independent full-field/PIT validation remains
**FALSE**.

If an ATG full-field source **does** exist at or before the conservative
cutoff, it is a veto when any of these occur:

- Provider \`passed\` is not explicitly \`true\`, including \`null\`,
  missing, zero, false, invalid value.
- The named matched/active runner counts are not real integers or contradict
  each other (\`matched != active\`, negative totals, or active below two).
  Booleans must never pass as integer runner counts.
- Any runner has an explicit error \`reason\` or \`schema_ok=false\`.
- Runner-list or provider \`reasons\` payload has an invalid type, or the
  provider explicitly lists rejection reasons.
- Existing source-revision collisions at the same instant, invalid observed
  clocks, or invalid source start clocks, as implemented in PR #115.

Such conditions now force both research completeness booleans to false,
with concrete \`full_field_rejection_reasons\` preserved. The snapshot
timestamp cutoff still prevents a **later** failed source claim from being
retroactively backdated into prior readiness.

\`source_published_at_utc\` is still only self-reported optional metadata:
this research-source diagnostic does not independently prove original
publisher first release, stable roster identity, T−4, or full-day denominator.

## Boundaries and tests

No market/probability models, Champion/V3.3.12, stakes, settlement,
production watcher, database schema, original provider source bytes,
scheduler, or real money movement are changed.

New offline source-negative tests deliberately construct fully populated
fundamental/market snapshots but explicitly failed ATG corroboration,
invalid runner count, individual runner errors, malformed provider reasons,
and missing/incorrect runner lists. They require **zero** claimed complete
fields. The positive fixture may still report *provisional* completeness,
but \`roster_pit_verified\`, \`prospective_t4_success_proven\` and BET
remain false.

Use the existing archived original CORE-003 time-recheck job and full CI
on exact PR HEAD, then independent HQ approval. A successful check of the
diagnostic does not count as a functional CORE-001/002/003 PIT acceptance.
