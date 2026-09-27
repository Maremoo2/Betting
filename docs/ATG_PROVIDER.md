# ATG read-only enrichment provider

ATG is used only as a **market-free enrichment source for Swedish trot runners**.

## Public endpoints

The adapter uses two public read-only racing-info surfaces observed in open-source
collectors and verified by the HBI live smoke workflow:

- `https://horse-betting-info.prod.c1.atg.cloud/api-public/v0/calendar/day/{date}`
- `https://www.atg.se/services/racinginfo/v1/api/games/vinnare_{race_id}`

The calendar resolves the Rikstoto race to an ATG race by date, normalized track name
and race number. The game response then supplies the runner horse object.

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

ATG enrichment is not a substitute for Rikstoto's canonical field. If a runner cannot
be aligned, it remains in the field with missing history. Coverage then determines
whether the race is shadow-bet eligible.

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
