# Betting – prioritert byggeplan etter CORE-002 (30.10.2026)

**Milepæler i den nye Core-retningen:** CORE-001 (ett historisk løp) og CORE-002 (hel historisk dag) er ferdig **lokalt**, ikke integrert i GitHub.

| # | Prioritet | Milepæl | Status |
|---:|---|---|---|
| 1 | P0 | Komplett datainnhenting for alle hester | Delvis: T−4 fundamentale snapshots mangler i 20/31 løp |
| 2 | P0 | Full flerfaktor fundamentalmodell | Ikke ferdig: Champion bruker bare totalstarter/seire |
| 3 | P0 | Egen p(win) for alle hester | Baseline virker ved komplett felt, 93/201 kjente aktive i dagutvalg |
| 4 | P0 | Fair odds, minsteodds og EV | Lokal baseline ferdig for 93 hester; grensen ukalibrert |
| 5 | P0 | Én komplett løpsanalyse | **CORE-001: lokal baseline ferdig** |
| 6 | P0 | Hele historiske løpsdager | **CORE-002: lokal dagmotor/audit ferdig**; 9/31 vurderte løp |
| 7 | P1 | Prospektiv kalibrering og lønnsomhetsmåling | Ikke tilstrekkelig evidens ennå |
| 8 | P2 | Stabil Watcher | Tidligere prototyper; ikke prioriteres før kjernedekning |
| 9 | P3 | Avansert backup og drift | Utsatt |
| 10 | P3 | Operativ betting | Ikke kvalifisert; kun Shadow/research |

## Neste – CORE-003 (første reelle blokkering)

1. Løft canonical roster ved eller før T−4 for alle travløp (12/31 mangler i arkivet).
2. Sikre komplette fundamentalsnapshots for hele feltet (20/31 mangler ved T−4).
3. Etterprøv markedsdekning (19/31 mangler ved T−4), uten å presse inn odds i p(win).
4. Skaff faktisk nyere form og løpskontekst: siste fem, distanse, startmetode/spor, nivå, kusk, tillegg/galopp, historisk kilde- og tidsstempelgrunnlag.
5. Gjenta identisk CORE-002 audit ved T−4, og øk dekning før flerfaktormodell/promotering.

**Fremdriftsmål:** antall løpsposter med komplette T−4-data, andel kjente hester med gyldig p(win)/EV, kvalitet/kalibrering over tid. Ikke antall nye infrastrukturmoduler.
