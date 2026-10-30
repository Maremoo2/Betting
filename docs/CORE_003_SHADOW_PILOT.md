# CORE-003 – Isolert kildeinnhentingspilot

## Status / avgrensning

Ny, separat GitHub Actions-workflow: `CORE-003 Isolated Source Coverage Pilot`.
Den kjører kun **kildeinnhenting**, uten Champion, EV-beslutninger eller spill.
Workflowen bruker **egen** `data/core003-pilot.sqlite` og **eget** artifact
`core003-pilot-state`. Den leser eller skriver **aldri** `hbi-state` og kan
ikke levere data direkte til dagens Watcher. Ingen endringer i V3.3.12.

## Tidsplan og kjøring

- Ved endring i **pilotens egen workflow-fil på `main`** startes en ekstra, engangs bootstrap-kjøring via en snever push-trigger; vanlige kodepush utløser ikke kildeinnhenting. Oslo-tidsvinduet gjelder også her.

- Cron hvert 15. minutt i UTC-vinduet 07–21. Python gate tillater bare 09:00–21:59 Europe/Oslo.
- Første kjøring starter fra tom, skjemaopprettet database. Senere kjøringer
  gjenbruker bare siste **isolerte** pilot-artifact på `main`.
- Hver kjøring kan hente høyst **4 oppgaver**, blant kjente travløp de neste
  **90 minuttene**. Ingen innhenting etter T−4.
- Manuell `workflow_dispatch` bruker *preview* som standard. Velg
  `execute=true` for å hente kilder; ingen ekte spill i noen modus.
- Kjøringer er serialisert i egen concurrency-gruppe, og påvirker ikke
  `hbi-state-writer` eller dagens Shadow Watcher.

## Måling

`core003-pilot-report.json` inneholder for samme faste sett kommende løp:

- Antall med startliste (registrert roster; ingen PIT-bevis for roster).
- Antall aktive hester med komplett, kildemerket historikk.
- Antall løp med verifisert fullfelt-historikk i datakohorten.
- Antall løp med komplett vinnerodds-kohort.
- Antall løp der begge datakohortene er komplette.
- T−4-kappede tidsstempler, planlagte og utførte kildeoppgaver, kildefeil,
  og eksplisitte differanser før/etter.

Rapporten bruker eksisterende `plan_prefetch` og
`_cohort`/`_verified_fundamentals`/`_market_complete`.
Den **beviser ikke** fullt tidsstemplet startliste, framtidig T−4 readiness,
kalibrerte sannsynligheter eller lønnsomhet. Data etter T−4 teller ikke.
Ved en live-kjøring må kilde- og rapportartifact inspiseres før vi hevder
bedre datadekning. Ikke overfør isolerte pilot-data inn i produksjonsdatabase
uten separat gjennomgått migrering.

## Kontrollkommandoer

```bash
hbi --db data/core003-pilot.sqlite init-db
python -m hbi.core_shadow_pilot --db data/core003-pilot.sqlite --out pilot.json
# Frivillig eksplisitt live-kildepilot (fortsatt ingen betting):
python -m hbi.core_shadow_pilot --db data/core003-pilot.sqlite --out pilot.json --execute
```

Ingen periodisk oppgave kan garantere T−4-dekning hvis leverandørkilder mangler
eller kjøres for sent. Sammenlign rapportene over flere løpsdager før CORE-004.
