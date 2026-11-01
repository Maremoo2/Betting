# P0 FR – strict original cross-provider calendar join (read-only diagnostic)

## Observed current production failure, not a guessed schema repair

The original HBI Provider Live Smoke (run 41293991327, 2026-11-01) returned
\`NO_FULL_FIELD_LIVE_PASS:FR\` and \`NO_PROVIDER_RACE\` for French **Laval**,
Rikstoto \`RIKSTOTO:F1_NR_2026-11-01:4\` (18 canonical runners).
In the same archived run, separate official ATG calendar research found
**Vincennes** (\`2026-11-02_63_1\`, 13 ATG runners), with no evidence these
are the same date, race, track, field or horses. LeTROT horse subpage
returned \`LETROT_HORSE_SCHEMA_UNAVAILABLE\`. A populated horse statistics
object for another meeting does not authorize copying or joining them to Laval.

## New source audit

\`python -m hbi.fr_source_join_audit --horizon-days 7 --output fr-identity.json\`
performs *bounded GET-only discovery*: one original Rikstoto race calendar and
at most seven ATG French day calendars. Every future canonical FR trot race
is compared to ATG by independent country, sport, exact canonical/observed
hippodrome (only the existing vetted Paris-Vincennes alias), exact race number,
unique candidate, provider's explicit "upcoming" status and UTC start tolerance
of max 300 seconds. No generic date- or country-only joins, no implicit horse
ID crosswalk, no betting odds, market prices or horse-history transplants.

Every diagnosis carries URL/HTTP status, source race identity and hash of the
*canonicalized parsed ATG JSON* (NOT the raw HTTP response body). Rikstoto's
raw GET response SHA256 is recorded when provided. Both are **observation
timestamps** not attestations of independent publisher *first publication*.
If no overlapping official race exists, the actionable gate is source availability:
get a truly same-race independent history source, not more lenient name joins.

Statuses:
- \`NO_IDENTICAL_FR_RACES_ACROSS_OFFICIAL_SOURCES\`: source program overlap absent.
- \`FR_CALENDAR_MATCH_FOUND_FULL_FIELD_STILL_UNVERIFIED\`: exact calendar identity
  exists, but not horse-name/number, scratched, start identity, lifetime history,
  letrot counts, PIT timestamp, final release.
- \`INCOMPLETE_ATG_ORIGINAL_CALENDAR_SOURCE\`: provider failure, never a PASS.
- \`RIKSTOTO_ORIGINAL_CALENDAR_NOT_VERIFIED\`: canonical source missing.
- \`NO_CANONICAL_FR_FUTURE_RACES_IN_SOURCE_WINDOW\`: no eligible denominator,
  never successful country coverage.

\`.github/workflows/fr-source-join-audit.yml\` runs actual live source
diagnosis on exact PR HEAD and distinct red-path synthetic source tests. It
does not change \`provider_coverage.json\`, \`full_field_gate\`, live smoke,
existing model, betting stake or any decision policy. A green diagnostic run
means *code successfully explained or found exact calendar overlap*; it does
**not** mean \`FULL_FIELD_ONLY_V1\`, France production eligible, PIT certified
or value betting approved. Existing \`HBI Provider Live Smoke\` continues to
fail until genuine full-field historical evidence works.

This is a source/coverage roadmap engineering diagnostic, not a standalone
repair for an unavailable original provider feed. Do not downgrade independent
LeTROT full-field corroboration, infer publication at T-minus-4 minutes, or
grant BET based on this report.
