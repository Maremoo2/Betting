# Rikstoto read-only provider

HBI uses Rikstoto only as a **read-only research data source**. There is no login,
account access, purchase endpoint, ticket submission or real-money execution in this
repository.

## Evidence levels

Endpoints are tagged by provenance rather than silently assumed to be current.

### USER_VERIFIED

The project owner supplied a live response from:

- `https://www.rikstoto.no/api/settings/urls`

The response identifies `https://www.rikstoto.no` as both RikstotoHost and Host.

### LIVE_SMOKE_VERIFIED

A GitHub Actions live smoke run on 2026-09-27 verified:

- `/api/racedays/{raceday}/starts`
- current raceday discovery
- current Vinner market rows

The `/starts` payload is now the canonical live race field. It exposes start number,
horse name/registration, driver, extra distance and scratch state without requiring
the retired program contract.

### OPEN_SOURCE_OBSERVED

Public third-party collectors contain concrete request code and historical response
fixtures for these Rikstoto endpoints:

- `/api/racedays/`
- `/api/results/racedays/{from}/{to}/list`
- `/api/game/{raceday}/betdistribution/winodds/{race}`
- `/api/game/{raceday}/betdistribution/placeodds/{race}`
- `/api/game/{raceday}/odds/tv/{race}`
- `/api/game/{raceday}/odds/t/{race}`
- `/api/racedays/{raceday}/scratched`
- `/api/racedays/{raceday}/raceInfo`
- `/api/results/racedays/{raceday}/raceresults`
- `/api/results/raceDays/{raceday}/{race}/completeresults`

Research references:

- https://github.com/vskaret/rikstoto
- https://github.com/youreakim/Horses

The vskaret repository includes historical response fixtures showing win rows with
`startNumber / odds / lastUpdated`, place rows with
`startNumber / minOdds / maxOdds / lastUpdated`, and combination rows for twin and
triple products.

This is evidence of the public contract being used historically. It is **not** a
guarantee that every endpoint remains available today. HBI therefore records HTTP
status, latency and errors for every provider fetch.

### HISTORICAL_FRONTEND_INFERRED

Historical public Rikstoto frontend source exposes these paths:

- `/api/game/producttimeline/racedays/{raceday}`
- `/api/game/producttimeline/racedays/{raceday}/investment`
- `/api/game/program/{raceday}/{product}`
- `/api/game/program/{raceday}/{product}/addition`

Reference:

- https://github.com/yngvebn/ngCliWebpackSample

The old frontend used program additions to expose V-game investment percentages and
win/place statistics. Live smoke tests in September 2026 returned HTTP 404 for the old
`/game/program/...` contracts across multiple Norwegian and Swedish cards. They are
therefore **disabled from the live critical path**. The code may retain them for
explicit historical research, but scheduled shadow runs do not call them by default.

## Current product capability

| Product | Market collection | Automatic shadow decision | Automatic settlement |
| --- | --- | --- | --- |
| Vinner (V) | Yes | Yes, only with a full-field FUNDAMENTAL probability set | Yes |
| Plass (P) | Yes | Not yet | Settlement engine supported for explicit future P tickets |
| Tvilling (TV) | Yes | Not yet | Not until an official dividend contract is verified |
| Trippel (T) | Yes | Not yet | Not until an official dividend contract is verified |
| DD | Legacy pool context disabled by default | Not yet | Not yet |
| V4/V4X | Legacy pool context disabled by default | Not yet | Not yet |
| V64/V65 | Legacy pool context disabled by default | Not yet | Not yet |
| V75/V85 | Legacy pool context disabled by default | Not yet | Not yet |

This separation is deliberate. A product does not become shadow-executable merely
because odds or betting percentages are available. It also needs a validated
probability model, executable ticket-cost rules and an unambiguous official settlement
contract.

## Timestamp policy

Some historical Rikstoto examples expose local timestamps without an explicit UTC
offset. When an offset is missing, the provider adapter interprets the timestamp as
`Europe/Oslo` and immediately stores UTC. The raw provider timestamp is retained in
provider metadata so this assumption remains auditable.

The watcher also stores:

- collector observation time
- provider `lastUpdated` time when available
- target T-4 time
- actual decision time
- execution latency from ideal T-4

This lets later research distinguish provider latency from model/runner latency.


## Canonical live field

HBI now uses:

`/api/racedays/{raceday}/starts`

as the canonical pre-race runner field. Every snapshot is timestamped when observed and
stored point-in-time. No market variable is copied into the fundamental feature store.

Rikstoto `/starts` does not currently expose the lifetime starts/wins needed by the
first empirical-win shadow model. Therefore:

- Swedish trot runners can be enriched from the separate public ATG read-only feed.
- Norwegian runners are stored as `FIELD_ONLY_RIKSTOTO` until a verified independent
  pre-race history source is available.
- Missing history forces `CAUTION / NOT_EXECUTABLE`; it is never imputed from odds.

See [ATG provider](ATG_PROVIDER.md) and
[Fundamental Shadow Champion v1.1](FUNDAMENTAL_CHAMPION_V1.md).
