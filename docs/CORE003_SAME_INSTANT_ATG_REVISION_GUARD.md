# CORE-003 P0 – Same-instant source revision conflict hard gate

## Source-backed defect

The previous \`core_shadow_pilot._atg_history_source_diagnostic\` selected
the first record returned by SQL \`ORDER BY observed_at_utc DESC\`, even if
**two different ATG full-field payloads shared exactly that same observed
instant**. SQLite text ordering can also select by UTC offset *string*
rather than chronological time. An earlier conflicting source instant could
be hidden by a unique later revision. All of these cases are unacceptable
for any prospective source-readiness numerator.

## New fail-closed research behavior

- Parse observed source clocks into aware UTC datetimes for eligibility and
  latest-cohort selection; do not infer times from lexicographic ordering.
- For **every** retained ATG full-field observation through the *existing
  conservative canonical T−4 cutoff*, group original captured payload bytes
  by normalized UTC instant. Distinct bytes at the same instant constitute
  \`CONFLICTING_SAME_INSTANT_ATG_FULL_FIELD_SOURCES\`, even when a later
  recorded revision has only one payload. Identical repeat copies are not
  counted as a conflict.
- An invalid/missing source observation clock results in
  \`ATG_SOURCE_OBSERVATION_CLOCK_INVALID\`; no safe source eligibility may
  be assumed from such a row. A malformed JSON body or source clock
  remains unsuitable for a model.
- Force \`history_complete_as_of_t4=false\` and
  \`win_market_complete_as_of_t4=false\` for any flagged source conflict,
  rather than selecting a convenient payload. This is deliberately
  stricter than a mere no-betting gate because a research source
  readiness count must also not look green.
- Keep \`roster_pit_verified=false\`,
  \`prospective_t4_success_proven=false\`, \`model_invocations=0\`
  and \`bet_count=0\` for the pilot. No edits to \`hbi-state\`,
  frozen market data, Champion/V3.3.12, stake, live provider endpoints
  or model.

## Validation

\`tests/test_core_shadow_pilot.py\` has additional distinct synthetic
regression cases for two differing full-field payloads at the exact
same instant, identical duplicate source copies, older conflicting
records hidden by a later valid record, UTC offset spelling variants,
and invalid source observed times. The separately existing
\`CORE-003 Historical Clock Recheck (Read Only)\` action replays an
*actual pinned archived* six-race source pilot and rejects any false
source readiness from a later start-clock revision. It never certifies
independent provider publication at the time of release.

**Exit gate:** this PR can improve source integrity while PIT certified
races remain **zero**. Formal CORE-001/002/003 acceptance additionally
requires original source hashes, all physical races in a complete
day denominator, publication-first timestamps, full-field and market
lineage and independent HQ authorization of the exact HEAD.
