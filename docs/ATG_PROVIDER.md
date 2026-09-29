# ATG read-only enrichment provider

ATG is used only as a **market-free enrichment source when its live race feed can cover the exact Rikstoto race and every active runner passes the full-field contract**.

## Public endpoints

The adapter uses two public read-only racing-info surfaces observed in open-source
collectors and verified by the HBI live smoke workflow:

- `https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/{date}`
- `https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{race_id}`

The calendar resolves the Rikstoto race by country, date, normalized track name,
race number and, when needed, a strict start-time fallback. The game response then
supplies the runner horse object. Country is therefore a routing hint, not a permanent
allow-list.

## Fundamental whitelist

Only these kinds of fields are allowed into the fundamental snapshot:

- horse identity / registration mapping
- age and sex
- trainer identity
- lifetime starts
- lifetime first/second/third places
- lifetime earnings
- start number / distance metadata

ATG game responses can also contain pool/odds data. HBI **does not persist those
fields into the fundamental feature store**. The raw fundamental JSON is rebuilt from
a whitelist rather than storing the original ATG start object.

The v1.1 Shadow Champion currently uses only lifetime starts and lifetime wins. The
other fields remain candidate challenger blocks.

## Point-in-time treatment

ATG enrichment is fetched during the same pre-race watcher run as the Rikstoto field.
The observation time becomes `feature_as_of_utc`. A feature timestamp later than the
decision timestamp is rejected by the point-in-time validator.

ATG enrichment is not a substitute for Rikstoto's canonical field. HBI now applies an
all-or-nothing **FULL_FIELD_ONLY** contract: every active runner must be identity
matched and expose age, sex, trainer, lifetime starts, first/second/third placings and
lifetime earnings. If one active runner fails, model-facing history is withheld for
the entire race and the race becomes field-only / NOT_EXECUTABLE.

Identity matching is auditable. Registration-ID matches receive confidence 1.00;
an exact normalized horse-name + start-number match receives 0.98. Anything weaker is
not accepted.

## Live smoke result

On 2026-09-27 the GitHub live smoke workflow selected Mantorp race 1 for 2026-09-28:

- 11 Rikstoto runners
- 11 runners with matched ATG lifetime history
- history coverage: 100%
- `FUNDAMENTAL_CHAMPION_V1_1`: `OK`
- shadow eligibility: true
- 11 current Rikstoto Vinner market rows
- provider fetch failures: 0

This verifies the integration contract, not predictive profitability.


## International live verification — 2026-09-29

The multi-country smoke workflow discovered 165 Rikstoto races across CH, DK, ES, FR,
NO and SE and probed one future Vinner race per country.

Current full-field verification:

| Country | Example track | Active runners | Full market-free history | Status |
| --- | --- | ---: | ---: | --- |
| SE | Visby | 12 | 12/12 | FULL_DATA |
| DK | Ålborg | 8 | 8/8 | FULL_DATA |
| NO | Bjerke | 9 | 0/9 exposed because one runner failed the all-or-nothing gate | FIELD_ONLY |
| FR | Chantilly | 16 | 0/16 | FIELD_ONLY |
| CH | Avenches | 6 | 0/6 | FIELD_ONLY |
| ES | San Sebastian | 7 | 0/7 | FIELD_ONLY |

The resolver will automatically admit a future race from any country if the same
strict contract passes. This avoids hard-coding countries as trusted when provider
coverage changes.
