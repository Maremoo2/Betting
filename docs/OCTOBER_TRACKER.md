# Oktober 2026: evidens og fremdrift

Trackeren leser den faktiske SQLite-tilstanden uten å skrive til databasen,
endre Champion, registrere en Challenger eller plassere spill. Manglende database
er en feil; den opprettes aldri som en tom, tilsynelatende frisk produksjonsdatabase.

## Åpne trackeren

De daglige arbeidsflytene **HBI V1 System Audit** og **Nightly Shadow Settlement**
bygger `research-v1/october-tracker.html` og `october-tracker.json` fra gjenopprettet
produksjonsdatabase. Last ned siste evidensartefakt i GitHub Actions og åpne HTML-filen.
Dashboardet fungerer uten nett, har landfilter, og viser tidspunktet for øyeblikksbildet.
Det er ikke en live-tilkobling; neste kjøring lager et nytt øyeblikksbilde.

Lokalt, med en ekte kopi av produksjonsdatabasen:

```powershell
python -m hbi.october_tracker --db data/hbi.sqlite --output-dir research-v1
```

Ingen lokal testdatabase er produksjonsevidens. Rapporter beholdes i eksisterende
audit- og nattlige sikkerhetskopier. Audit-arbeidsflyten forsøker å bygge trackeren
også når integritetskontrollen feiler, så avvik forblir synlige.

## Fire milepæler

| Periode | Tracker | Hva krever videre arbeid? |
| --- | --- | --- |
| 1.–7. oktober | Daglig drift i SE/DK/NO/FR, feltdekning, avvisninger, beslutninger, T−4 og oppgjør | Etter 7. oktober kreves sluttkontroll; dato gir aldri automatisk godkjenning. |
| 8.–14. oktober | Tidligere starter per hest og prisforløp som separate tellere | Karrieresammendrag teller ikke som detaljerte starter. Manglende kontrakt vises som ikke implementert. |
| 15.–21. oktober | Fundamental, marked og kombinasjon på identisk kohort, med landfilter | 100 sammenlignbare løp åpner for en tidlig vurdering, ikke modellgodkjenning. |
| 22.–31. oktober | Registrerte Challengers med egne fremoverklokker | Historikk, minst 100 sammenlignbare løp og ferske beståtte integritetskontroller kan åpne for en manuell forskningsvurdering. |

Statusene viser arbeid og evidens, aldri automatisk ferdigstillelse. Forskningsvurderingen
må kontrollere dekningen av de nye variablene og begrunne én enkel hypotese før en
Challenger registreres. Trackeren foretar ingen registrering eller modellendring.

## Opptellingsregler

**Kvalifiserte løp** har en kanonisk Rikstoto-identitet og første fryste beslutning
i oktober for `SHADOW_RESEARCH_V1_EQUAL_LOG_POOL`, med Champion v1.1.
FULL_FIELD_ONLY kontrolleres igjen mot providerbevis og snapshots som faktisk var
tilgjengelige før beslutningen. Fundamentalmodellens kohort og hele aktive feltet
må samsvare. Alle tre sannsynlighetsfordelinger må være endelige, normaliserte og
ha nøyaktig samme aktive felt. Code SHA, governance-hash og gyldige policy-/prisobjekter
må finnes. Senere bedre data og andre modellversjoner kan ikke redde et avvist løp.

**Sammenlignbare løp** er den samme kvalifiserte kohorten med kjent vinner og et
oppgjørstidspunkt mellom løpsstart og rapporttid. Alle tre lag scores på samme løp.
Log loss, multiclass Brier og kalibreringsbånd beregnes fra de fryste fordelingene.
Forskjell mot markedet er deskriptiv; ingen signifikans eller dokumentert edge påstås.

50–100 løp er primært driftssjekk. 100–300 gir tidlige diagnoser. 500+ urørte,
kvalifiserte løp med resultat er et utgangspunkt for mer seriøs vurdering, ingen garanti.
Utvalgsmålene teller sammenlignbare løp, mens kvalifiserte løp vises separat.

**Økonomiske tall** inkluderer bare oppgjorte Winner-paper-spill i kvalifisert kohort,
med pris som samsvarer med fryst provenance, maksimalt 120 sekunders gammel quote,
beslutning innen fem minutter før start og pris over fryst minimumspris.
Stake, retur og P/L må stemme. CLV krever egen gyldig closing-pris og samsvar med
`log(available/closing)`. Ukjent P/L eller CLV vises som ukjent, aldri som null.
Tellere og eksklusjoner vises, også per land. Dette er en prisverifisert paper-måling,
ikke en simulering av likviditet eller garanti for gjennomførbar pari-mutuel sluttpris.

**Challenger-klokken** teller unike kvalifiserte fremoverhendelser først etter både
registrering, discovery cutoff og forward start; evalueringen må være etter start og
tilgjengelig ved rapporttid. Den deler ikke Champions historiske utvalg.

## Fremtidig kontrakt for detaljerte starter

Trackeren oppretter ingen historikktabell. Når ingestion bygges, kan den lese en
`horse_start_history`-tabell med `horse_id`, `historical_race_id`, `race_start_utc`,
`distance_m`, `race_class`, `track`, `finish_position`, `source_uri`,
`observed_at_utc`, `available_at_utc` og `market_free`.
Manglende felt, midlertidige TMP-identiteter, ikke-markedsfri historikk og ugyldige
tidsstempler avvises. Det dedupliseres på hest og historisk løp. Dette er en
innsamlingsopptelling; den beviser ikke at variablene var tilgjengelige før hver
modelleringsbeslutning eller at hele aktive feltet har tilstrekkelig historikk.

Prioriteten er datakvalitet, deretter sannsynligheter og så økonomi. Champion,
staking og modellformel står urørt. Ingen ekte penger eller automatisk promotering.
