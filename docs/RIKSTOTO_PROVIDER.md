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
win/place statistics. HBI treats these endpoints as optional: failure never invents a
replacement value and never blocks the core V/P/TV/T collector.

## Current product capability

| Product | Market collection | Automatic shadow decision | Automatic settlement |
| --- | --- | --- | --- |
| Vinner (V) | Yes | Yes, only with a full-field FUNDAMENTAL probability set | Yes |
| Plass (P) | Yes | Not yet | Settlement engine supported for explicit future P tickets |
| Tvilling (TV) | Yes | Not yet | Not until an official dividend contract is verified |
| Trippel (T) | Yes | Not yet | Not until an official dividend contract is verified |
| DD | Raw pool/program context when endpoint works | Not yet | Not yet |
| V4/V4X | Raw pool/program context when endpoint works | Not yet | Not yet |
| V64/V65 | Raw pool/program context when endpoint works | Not yet | Not yet |
| V75/V85 | Raw pool/program context when endpoint works | Not yet | Not yet |

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


## Market-free program fundamentals

HBI also reads the base public program contract through
`/api/game/program/{raceday}/{product}` when available. Historical Rikstoto frontend
types show that this payload contains runner facts and horse annual statistics.

For the fundamental feature store HBI explicitly excludes `program/addition` fields
such as win odds and investment percentages. The base program snapshot is timestamped
and frozen before the T-4 decision.

The first model using this feed is documented in
[Fundamental Shadow Champion v1](FUNDAMENTAL_CHAMPION_V1.md).
