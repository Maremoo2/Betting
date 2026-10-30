# BETTING-CORE-002 – Full historisk løpsdag (30. oktober 2026)

## Formål og resultat

Et fullstendig, **lesebasert** dagprogram for historiske travløp som gjenbruker `CORE-001` og uendret `FUNDAMENTAL_CHAMPION_V1_1`. Hver oppdaget løps-ID får status, alle identifiserte hester i vurderte løp får eksportert rad, og årsakene til manglende `p(win)`/EV dokumenteres. Ingen ekte spill eller autoriserte BET-signaler.

**Hovedanalyse:** arkivert løpsdato **28. oktober 2026**, eksakt T−4 minutter i forhold til oppført starttid for hver løps-ID.

| Måling | Arkivert resultat |
|---|---:|
| Alle løpsreferanser i inventar | 50 |
| Galopp utelatt fra travmodell | 7 |
| Kombinerte Solvalla/Bergsåker-produkter utelatt | 8 |
| Sannsynlige dobbelreferanser til samme Marseille-løp utelatt | 4 |
| Vurderte travløp, sannsynlig fysiske | 31 |
| Komplett smal Champion-baseline ved T−4 | **9/31 (29,0 %)** |
| Fundamentalt klare, men manglende odds | 0 |
| Blokkerte løp | 22 |
| Kjente aktive hester i vurderte løp | 201 |
| Med `p(win)`, fair odds og modell-EV | **93/201 (46,3 %)** |
| Eksporterte hesterader inkludert strøkne | 213 |
| Forsknings-WATCH / autoriserte BET | 47 / **0** |

**Solvalla-kortet:** 10 løp; 4 komplett smal baseline, 6 blokkert; 40/65 kjente aktive har `p(win)` og modell-EV, 19 forsknings-WATCH, 0 BET.

**Løp med komplett baseline per bane:** Bergsåker 3/9; Solvalla 4/10; Århus 2/8; Marseille Pont De Vivaux 0/4.

## Årsaker til udekkede løp

Grunnene overlapper for samme løp; summene skal **ikke** legges sammen:

| Årsak | Vurderte løp |
|---|---:|
| `NO_FUNDAMENTAL_COHORT_AS_OF` | 20 |
| `NO_WIN_MARKET_AS_OF` | 19 |
| `NO_CANONICAL_ROSTER` | 12 |
| `INSUFFICIENT_ACTIVE_FIELD` | 20 |
| `LOW_HISTORY_COVERAGE` | 2 |
| `FULL_FIELD_HISTORY_NOT_VERIFIED` | 2 |

For aktive hester i vurderte løp mangler følgende i valgte T−4-fundamentalsnapshots: `current_year_starts` 201/201, `current_year_wins` 201/201, `record_auto` 201/201, `record_volt` 201/201. Historiske totalstarter/seire mangler på 108 av 201. **Dette er snapshotdekning, ikke et bevis for at tilsvarende data er utilgjengelige i andre kilder eller i en separat kanonisk startliste.**

## Sporbarhets- og regnemetode

1. Leser hele `races`-inventaret for valgt dato, og markerer utelatte referanser eksplisitt i `races.csv`.
2. Skiller trav fra galopp; kombinerte track-produkter utelates som standard. Samme bane + løpsnummer med mindre enn 10 minutter mellom oppførte starter behandles som sannsynlig duplikatreferanse. Den med flest kjente roster-rader beholdes. Dette er en *heuristikk*, ikke sikker identifikasjon.
3. For hvert vurderte løp brukes **kun siste snapshot-kohort ved eller før T−4**, uten senere pris-, historikk- eller modellopplysninger. Ufullstendige kohorter kompletteres aldri med senere eller eldre snapshot.
4. Bruker eksisterende, uendret `historical_win_prior`: empirisk-Bayes historisk seiersrate med `prior_starts=6` og 80 % historikkdekning.
5. Ber om fullfelt/kildekontroll, beregner `p(win)` som summerer til 1 på komplette løp, fair odds `1/p`, eksperimentell WATCH-pris `fair*(1.05)*(1.05)` og teoretisk EV `p*odds - 1`.
6. Ingen BET-status. Tomme/udokumenterte data gir blokkering – ikke gjetning. `FUNDAMENTAL_ONLY` bevarer p(win) hvis markedet mangler, uten prisbeslutning.
7. Eksporterer `day_core.json`, `day_core.md`, `races.csv`, `runners.csv`, samt valgfritt separate tre rapporter for hvert vurderte løp.

## Test og reproduserbarhet

- 28 tidligere CORE-001-tester beholdt, nye CORE-002-tester dekker full dag, én bane, sannsynlige duplikater, ekskluderte produkter, alle hester, no-odds fundamental-only, kildefremtid, T−4, output, fixture, feilhandling og arkivparitet.
- Lite SQLite-uttrekk: `reports/core_002_28oct_fixture.sqlite` (~596 KiB), inkluderer 50 løp, 340 roster-rader, 228 historiske fundamentalrader, 238 markedsrader og 9 modelleringsloggposter. Ingen outcomes eller settlementtabeller.
- Hele `day_core.json` er identisk for dette utdraget og den opprinnelige arkiverte databasen, når samme algoritme og T−4 brukes.
- Testresultater, SHA-256 og patchcheck ligger i `reports/` og `manifest.json`.

## Begrensninger

Dette er en *historisk rekonstruksjon*. Uavhengig kildepubliseringstid, historiske endringer i startliste/oppført starttid, nasjonale markeder og faktisk tilgjengelige totalisatorpriser er ikke bevist. Archivert runnerliste kan inkludere etterfølgende korrigeringer. Startnummer, nyere form, løpsklasse, spor, distanse, kusk og tempo er ikke priset av Champion V1.1. WATCH=kun forskning. Ingen lønnsomhet, kalibrering eller reell value er validert. Systemet kontakter ikke providers i denne leveransen og har ikke fått bedre live-dekning.

**Neste:** CORE-003 innhenting av manglende kanonisk startliste og hele T−4-fundamentalfeltet, deretter flerfaktormodell og prospektiv evaluering.
