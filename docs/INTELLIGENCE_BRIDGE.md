# Scheduled Intelligence -> HBI Evidence Bridge v1

The bridge connects ChatGPT pre-watch/research to the HBI research database without allowing an LLM to overwrite canonical race, market, model or betting state. Scheduled ChatGPT runs produce a structured evidence payload in the project conversation; an interactive authorized ChatGPT session relays that payload to the GitHub staging inbox. Scheduled runs do not attempt GitHub mutations because connector safety can block unattended writes.

## Authority boundary

Canonical source of truth:

```text
HBI SQLite
```

GitHub issue #18 (`HBI Intelligence Evidence Inbox (machine staging)`) is the
primary machine transport because GitHub Actions can read it with the built-in
`GITHUB_TOKEN` and no external credential. The worksheet `HBI_EVIDENCE_INBOX`
remains an optional human-readable staging/mirror path when Google Sheets credentials
are configured. Neither transport is the betting database. HBI validates staged rows
and imports accepted evidence into `intelligence_evidence`.

The old manually maintained RACES/SNAPSHOTS/BETS_OUTCOMES tabs may remain useful for
historical reference or dashboards, but they are not authoritative over canonical HBI
state.

## Intended flow

```text
official/public sources
        |
scheduled ChatGPT intelligence scout
        |
GitHub issue #18 comments (primary staging)
        |
optional HBI_EVIDENCE_INBOX mirror
        |
HBI validation / race identity resolution / PIT checks
        |
intelligence_evidence (canonical research record)
        |
Research Observatory / future Challenger research
```

The bridge never writes directly to:

- provider market snapshots;
- closing prices;
- official outcomes;
- runner history;
- model probabilities;
- Champion configuration;
- BET/PASS decisions;
- stakes;
- settlement;
- model promotion.

## Primary GitHub issue transport

The scheduled scout posts an append-only comment to repository issue #18 using this
envelope:

```text
HBI_INTELLIGENCE_BRIDGE_V1
{...one JSON evidence row...}
```

A JSON array is also accepted. Comments without the exact bridge envelope are ignored.
The hourly and nightly workflows import issue #18 with `issues: read` permission and
the built-in GitHub Actions token. This makes the core bridge independent of Google
Sheets secrets.

Historical machine evidence comments should not be edited to rewrite an observation.
A correction is appended as a new row with a new `inbox_id`.

## Optional worksheet contract

The optional staging/mirror worksheet is `HBI_EVIDENCE_INBOX`.

Columns:

1. `inbox_id`
2. `observed_at_utc`
3. `provider`
4. `provider_raceday_key`
5. `race_number`
6. `race_id`
7. `selection_id`
8. `event_type`
9. `claim_text`
10. `source_uri`
11. `source_type`
12. `source_timestamp_utc`
13. `source_time_basis`
14. `confidence`
15. `materiality`
16. `evidence_status`
17. `prewatch_score`
18. `policy_version`
19. `extractor`
20. `notes_json`

`race_id` may be blank if the row includes
`provider + provider_raceday_key + race_number` and HBI can resolve that reference.

## Allowed event types

V1 accepts only research/evidence events:

- `TRAINER_COMMENT`
- `DRIVER_CHANGE_CONTEXT`
- `JOCKEY_CHANGE_CONTEXT`
- `SCRATCH_NOTICE_CONTEXT`
- `TRACK_CONDITION`
- `WEATHER_CHANGE`
- `EQUIPMENT_CHANGE`
- `TROUBLED_TRIP_EVIDENCE`
- `RACE_SHAPE_HYPOTHESIS`
- `LATE_NEWS`
- `INJURY_VET_NOTICE`
- `CLASS_CHANGE_CONTEXT`
- `DISTANCE_TRACK_FIT`
- `PREWATCH_DISCOVERY_SIGNAL`
- `OTHER_RESEARCH_EVIDENCE`

Canonical facts/actions such as `MARKET_SNAPSHOT`, `RESULT`, `PREDICTION`,
`BET_DECISION`, `STAKE` and `SETTLEMENT` are rejected by design.

## Point-in-time status

Evidence can be stored even when it is not suitable for prospective evaluation.

A row is marked `pit_eligible=1` only when:

- it was observed before race start;
- a source timestamp is known;
- the source timestamp is not later than the observation timestamp;
- the timestamp basis is `PUBLISHED` or `OBSERVED`;
- the evidence status is `VERIFIED` or `CORROBORATED`.

Even PIT-eligible intelligence remains:

```text
research_only = 1
production_feature_eligible = 0
```

in Bridge v1.

A future feature must pass normal Challenger/OOS governance before qualitative evidence
can affect production probabilities.

## PRE-WATCH score

The legacy/chat PRE-WATCH 0-100 score may be stored in the inbox as
`PREWATCH_DISCOVERY_SIGNAL` or alongside another evidence event.

It is a discovery/research signal only. It is not p(win), fair odds, edge or a betting
instruction.

This allows later research such as:

- whether high PRE-WATCH races contained more genuine model-market disagreement;
- whether they produced higher CLV;
- whether particular qualitative hypotheses were informative;
- whether score components add incremental value after market information.

## Import behavior

The hourly HBI PRE-WATCH workflow and nightly settlement workflow always attempt the
GitHub issue inbox import. They also attempt the Google Sheets inbox import when Sheets
secrets are configured.

The importer:

1. reads the staging worksheet;
2. deduplicates by `inbox_id`;
3. resolves the canonical race;
4. validates runner identity when `selection_id` is present;
5. rejects forbidden canonical event types;
6. validates timestamp/confidence/score ranges;
7. computes PIT eligibility;
8. stores accepted rows in `intelligence_evidence`;
9. stores accepted/rejected import audit rows in `intelligence_bridge_imports`.

Repeated imports are idempotent.

## Failure behavior

The bridge fails closed.

Bad rows are recorded as rejected with a reason such as:

- `UNKNOWN_RACE_ID`
- `UNRESOLVED_PROVIDER_RACE`
- `UNKNOWN_SELECTION_ID`
- `CANONICAL_EVENT_FORBIDDEN`
- invalid/naive timestamps
- invalid confidence or PRE-WATCH score
- missing source URI or claim

Rejected intelligence cannot modify canonical market/model/betting state.


## Scheduled transport boundary

Scheduled ChatGPT runs must not claim that they wrote directly to GitHub. When new resolvable evidence exists, the run emits:

```text
HBI_EVIDENCE_PAYLOAD_V1
[ ...validated-shape candidate rows... ]
```

in the project conversation. The next interactive authorized ChatGPT turn may deduplicate and append that payload to GitHub Issue #18. The existing HBI workflow then imports the issue, performs canonical race/runner resolution, validates timestamps and PIT status, and records accepted/rejected rows.

This is deliberately human-in-the-loop. A scheduled connector write failure is therefore no longer a bridge failure; no scheduled GitHub write is attempted. Evidence is not considered staged until the interactive relay succeeds.

The transport boundary does not weaken model governance: imported rows remain `research_only=1` and `production_feature_eligible=0`.
