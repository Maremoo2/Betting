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


## Additional offset-normalized timestamp safety in source-only pilot

The historical \`race_core_review._cohort\` research helper uses SQLite
text comparison of ISO timestamps. It may admit an *actually future*
source row whose representation happens to sort earlier as a string:
\`11:55-01:00\` is \`12:55 UTC\`, not available at \`12:00 UTC\`.
The same hazard exists for \`feature_as_of_utc\` and an optional
\`provider_updated_at_utc\` on market snapshots.

Without altering the existing formula or shared helper, the isolated pilot
now **rechecks all selected fundamental and WIN snapshot row clocks** as
actual UTC datetimes against its conservative existing T−4/as-of cutoff.
Future or malformed selected clocks set both provisional completeness
booleans to false and record
\`selected_snapshot_timestamp_problems\` with the specific invalid
source timestamp field. Correct genuinely historical snapshots remain
provisional only; no source-first-publication assertion is made.

This is a **false-positive rejection guard**, not a complete repair for all
historical timezone-normalization issues in \`_cohort\`. A genuinely past
offset-formatted snapshot excluded by the old lexical query can still
result in a conservative false negative, never automatic PIT certification.
Separate centrally reviewed work would be required to replace that
shared research selection helper safely.


## Malformed source timestamps in prefetch planner

The same offset/time pathology affected \`core_prefetch.plan_prefetch\`.
It previously parsed the selected SQL cohort timestamp directly during
staleness checks; e.g. \`1999-invalid-source-clock\` could crash the
whole isolated pilot *before* the source-readiness veto was reached.
The plan now validates **all selected** fundamental \`observed_at_utc\`,
\`feature_as_of_utc\`, market \`observed_at_utc\`, and optional
\`provider_updated_at_utc\` as aware UTC instants not after the
planning observation time. Invalid/future clocks set completeness to
false and request re-fetch; no exception, no automatic market or
fundamental completion. This remains a research-only queue; a source
refresh is not a published PIT record or a BET signal.
