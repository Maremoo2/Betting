# CORE-003 — Validering og avgrensning

Dato: 2026-10-30. Lokal, skrivebeskyttet historisk analyse og injiserbar innhentingsworker. **Ikke production / ikke BET**.

## Kode levert

- `src/hbi/core_prefetch.py` — prioriterer manglende starts/historikk fra 4–90 min før start, vinnerodds i siste 12 minutter og dataoppfriskning ved T−8..T−4; `execute_prefetch` bruker eksisterende collector-metoder; ingen modell/oddsvekter endret.
- `src/hbi/core_prefetch_worker.py` — opt-in, manuelt kjørbar `discover → plan → fetch → replan`, med `--execute` for provider I/O; ikke aktivert i workflow.
- `src/hbi/core_gap_audit.py` — dokumenterer observasjon før/etter arkivert T−4 fra `provider_payloads`.
- `src/hbi/core_gap_fixture.py` — utvider CORE-002-fixture med kun providerreferanser og kildetidsstempler. Ingen rå provider body/settlement.
- `src/hbi/core_feature_sidecar.py` — løfter observerte 2026-årstall (`starts`, `earnings` i ukjent kildenehet) fra fullfeltverifisert `raw_json` til et separat datasett. Rører ikke Champion eller historiske T−4-valg.

## Faktisk kildeaudit 28.10.2026

- 50 inventarreferanser, 31 vurderte sannsynlige fysiske travløp, 22 blokkert, 9 smale Champion-baselines ferdig. 93/201 kjente aktive hester med p(win) (uendret fra CORE-002).
- 11 løp uten arkivert startsforespørsel; 7 startsforespørsler kun etter T−4; 11 uten arkivert historikkforespørsel; 8 historikksvar først etter T−4; 2 med pre-cutoff historie som ikke var fullt verifisert. Kategoriene overlapper.
- Årsdatasidecar gjenvinner starts/earnings for 93 verifiserte aktive hester, uten etterpåklokskap. Ingen årsvinnere/auto- eller voltrekorder er gjettet.
- Kompakt fixture: 50 raser, 50 provider race refs og 136 råkilde-tidsstempler (bare metadata). Originalarkiv og kompakt fixture gir byte-identisk kildeaudit og feature-sidecar.

## Tester

Full pakke (CORE-001 + CORE-002 + CORE-003): **121 bestått, 1 hoppet over** på lokal Python/pytest. Den ene hoppede testen krever separat historisk originalarkiv via prosjektets testbetingelse. Originalarkivet ble brukt direkte i de nye kilde- og årsdatarapportene. Syntetisk collector testet at en plan kan resultere i oppfylt historikk- og markedskohort; ingen reelle HTTP-kall.

## Begrensninger

- Historisk CORE-002-dekning er **fortsatt 9/31**. Å flytte kilder som først ble observert etter T−4 bakover ville vært data-lekkasje; vi gjør det ikke.
- `provider_payloads` viser bare hva systemet arkiverte, ikke når upstream først publiserte informasjonen.
- Arkivert `runners`-tabell er muterbar og viser ikke selvstendig når roster ble kjent. Historisk prefetcheksempel er derfor kun en hypotetisk prioritetskø, ikke faktisk prospektiv tilgjengelighet.
- Ny collector-kjøring er testet med fake provider, ikke autentisert/live Rikstoto eller ATG; nye felt er ennå ikke koblet inn i Champion/flerfaktor-modell.
- `current_year_earnings_source_units` er rå numerisk kildedata, ikke NOK-valuta. Ingen odds/EV-kalibrering er dermed bevist.
- Koden er klar for review, men patchene er **ikke** pushet, CI-testet på GitHub eller aktivert i noen produksjonsworkflow.

## Operativ neste steg

CORE-004: godkjent, begrenset Shadow-pilot som måler for hver oppdaget fysisk løpsreferanse om `starts`, historikk, fullfelt identitet og vinnerodds er samlet inn før T−4, og om hele feltet kan prises. Deretter flerfaktor-challenger (markedsfri prediksjon separat fra verdi-prising); hold fryst Champion V3.3.12 uendret.
