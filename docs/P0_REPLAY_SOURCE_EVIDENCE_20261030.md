# P0-REPLAY-001 – etterprøvbar historisk beviskjede (30.10.2026)

**Begrenset status:** Historiske avvik er årsaksforklart; V1 runtime replay og settlement er fremdeles **FAIL**. Denne rapporten er **ikke** korrigering, rapport-waiver, modellgodkjenning eller BET-autorisasjon.

## Primærgrunnlag

| Evidens | Verifisert |
| --- | --- |
| Baselinekode | `Maremoo2/Betting` main `e328c196ea236053536a9134e0b8dc89e26f0924`, merged [PR #80](https://github.com/Maremoo2/Betting/pull/80) |
| Ny produksjonsartefaktaudit på main | [HBI V1 System Audit #41107698547](https://github.com/Maremoo2/Betting/actions/runs/41107698547), audit ZIP artifact **13002050875**, generert 18:32 UTC |
| Fryst state for uavhengig diagnostikk | [Watcher #41105795195](https://github.com/Maremoo2/Betting/actions/runs/41105795195), `hbi-state` artifact **13001685408** |
| SQL-database / SHA-256 | `data/hbi.sqlite` **4f671ade4510247544c3b6a95e66f6a5c24681814fb4790adf98b847bf1b660e**, 526 364 672 bytes |
| Sikker lesemodus | `mode=ro&immutable=1`; før/etter SHA-256 identisk; ingen historiske writes |
| Dato-/kohortgrense | Dette beviser de **observerte** beslutningene i den eksplisitte arkiven. Det er ikke et tilfeldig eller prospektivt prøveutvalg. |

## Fersk systemaudit på faktisk gjenopprettet state

| Integritetsport | Resultat |
| --- | --- |
| Temporal | **PASS** |
| Provider | **WARN**: 11 observerte fetchfeil, hvorav 10 LeTrot og 1 Rikstoto |
| Runtime replay | **FAIL**: 304 sjekket, 425 hoppet over, 5 mismatch |
| Settlement | **FAIL**: 737 sjekkede poster, én uoppgjort Shadow-kupong etter 24t |

Ikke presenter grønn ren-database-test eller PR-CI som en PASS i disse to operasjonelle FAIL-portene.

## Fem uendrede historiske WATCH-beslutninger

Den uavhengige, skrivebeskyttede rekonstruksjonen viser at den **eksakte WIN-kohorten ved frosset `source_market_observed_at_utc`** gir samme normaliserte markedsfordeling som den lagrede modellen (maks absolutt feil = 0 i denne rekonstruksjonen). Lagrede proveniensodds gir derimot avvik, og alle fem matchende senere kohorter finnes i arkivet.

| Race ID | Vedhefting etter frosset beslutning | Maks avvik i lagret markeds-p fra vedheftet odds | Konklusjon |
| --- | ---: | ---: | --- |
| `RIKSTOTO:S2_NR_2026-10-09:5` | 9,411 min | 1,986 pp | Sen proveniens, kilde rekonstruert |
| `RIKSTOTO:MO_NR_2026-10-17:10` | 11,345 min | 3,734 pp | Samme |
| `RIKSTOTO:S4_NR_2026-10-21:9` | 6,164 min | 3,411 pp | Samme |
| `RIKSTOTO:S2_NR_2026-10-22:5` | 6,902 min | 3,354 pp | Samme |
| `RIKSTOTO:S3_NR_2026-10-25:11` | 11,200 min | 6,780 pp | Samme |

Alle fem var **WATCH, ticket_count=0**. Ingen av disse fem observasjonene er bevis på en feilaktig booket Shadow-kupong, men mismatchene forblir alvorlige for reproduksjon.

Den eksisterende `src/hbi/legacy_provenance.py` må fortsatt kreve *fullt aktivt felt* og en gyldig original kohort. Den nye, avgrensede forskningsendringen legger til reproduserbare SHA-256-fingeravtrykk for frossen input, eksakt kilde og senere tilknyttet proveniens. Den fjerner ikke P0-FAIL fra `src/hbi/replay_validation.py`. Ukjent, likt eller naivt tidsstempel skal ikke få klassifiseringen `LEGACY_LATE_PROVENANCE_SOURCE_RECONSTRUCTED`.

## Separat P0 settlement

[Issue #82](https://github.com/Maremoo2/Betting/issues/82): DK 14. oktober, Skive løp 6. `ticket_id=a55a504a-bc34-487d-aced-75326dcb2b59`; valg #8; papirinnsats 25 NOK, `SHADOW_BET`. Den lokale `outcomes`-tabellen viser vinner #5, men **ingen** komplett original resultat-/dividendepayload ligger i denne arkivkohorten. Derfor ingen antatt `-25` bokføring, ingen CLV-fabrikasjon og ingen tilstandsoppdatering.

## Neste milepæler / akseptanseporter

1. **Kodedel av P0 replay:** målrettede negative tester og full repository-CI på ny forsknings-PR, eksakte SHA/hashbevis og faktisk gjenopprettet arkivtest, med `DIAGNOSTIC_ONLY_NOT_PRODUCTION_CLEARANCE`.
2. **Uavhengig historisk adjudikasjon:** vurder et særskilt append-only kildedokument og formell HQ-beslutning. Ikke backfill/overskriv gammel proveniens; ikke sjul mismatch ved unntak eller juster toleransen.
3. **P0 settlement:** innhent autentisk `isComplete=true`, bekreftet #8-deltakelse/plassering og publisert vinnerdividende; replay på isolert kopi før en separat godkjent state-handling.
4. **CORE-003:** PIT-autentisert startliste, kildens publiseringstid, immutable versjonerte revisjoner ved T−4 over hele løpsdager og land. [Issue #83](https://github.com/Maremoo2/Betting/issues/83).
5. **CORE-004/P1:** verifiserte siste-fem-/klasse-/kuskdata, forhåndsregistrert modellprotokoll, urørt kronologisk OOS; inntil da `NOT_VALIDATED` og `REAL_MONEY_OFF`.

**Rollback:** Avvis ny forsknings-PR uten merge; originale arkiverte SQLite-/proveniensdata forblir uendret.
