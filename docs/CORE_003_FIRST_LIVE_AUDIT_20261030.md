# CORE-003 – Første prospektive Shadow-kildepilot, 30.10.2026

## Kilde og reproduserbarhet

- GitHub Actions: https://github.com/Maremoo2/Betting/actions/runs/41049804525
- Oppstart: 2026-10-30T11:41:04.234358Z; slutt: 2026-10-30T11:41:12.288784Z.
- Artefakter: `core003-pilot-report-41049804525` og `core003-pilot-state` (se workflow-kjøringen).
- Datagrunnlag: observert kildeinnhenting i **Östersund** (RIKSTOTO:S1_NR_2026-10-30), løp 3–6. Dette er **ikke Solvalla**.
- Kilder: Rikstoto startlister og ATG fullfeltskontroll, med tidsstempler fra første pre-start-kjøring.

## Faktisk resultat – før → etter

| Metrikk | Før | Etter | Differanse |
|---|---:|---:|---:|
| Løp i fast kohort | 4 | 4 | 0 |
| Løp med registrert startliste | 0 | 4 | +4 |
| Kjente aktive hester | 0 | 50 | +50 |
| Aktive hester med verifisert historikk | 0 | 35 | +35 |
| Løp med fullt verifisert historikk | 0 | 3 | +3 |
| Løp med komplett WIN-market | 0 | 0 | 0 |
| Løp med begge kildelag komplette | 0 | 0 | 0 |
| Spill / modellkjøringer | 0 | 0 | 0 |

4 kildeoppgaver ble utført. 243 løpsreferanser ble oppdaget, men **kun fire** kommende løp ble valgt i denne tidsavgrensede kjøringen. `FETCHED_NOT_PROVEN_COMPLETE` betyr at leverandøren returnerte data, ikke at hele feltet bestod verifikasjonen.

## Per løp

| Östersund | Aktive hester | Godkjent samlet historikk | T−4 cutoff UTC | Observasjon UTC |
|---|---:|---|---|---|
| Løp 3 | 10 | 10/10 | 12:03 | 11:41:08 |
| Løp 4 | 14 (1 strøket) | 14/14 | 12:25 | 11:41:10 |
| Løp 5 | 11 | 11/11 | 12:46 | 11:41:10 |
| Løp 6 | 15 | Blokkert, 14/15 i ATG source check | 13:06 | 11:41:12 |

I løp 6 rapporterte ATG `INCOMPLETE_RUNNER_HISTORY_OR_IDENTITY` for **nr. 8 Pave Jerkeld** med årsak `LIFETIME_BELOW_YEAR_TOTALS`. En enkelt kildeinkonsistens blokkerte hele fullfeltskohorten. Dette er korrekt etter eksisterende Champion-gate; ingen historikk eller sannsynligheter skal gjettes.

## Tolkning og neste verifisering

Denne første piloten beviser **tidlig innhenting av startliste og dokumentert historikk for 35 aktive hester**, men **ikke** komplett beslutningsgrunnlag ved T−4, ikke point-in-time-bevis for den muterbare `runners`-tabellen og ikke kalibrert betting.

Det opprinnelige WIN-odds-vinduet var 12 minutter før start, mens workflowen er planlagt hvert 15. minutt. Et pilotspesifikt 30-minutters vindu skal gjøre prisinnhentingen mindre sårbar for planleggingsforsinkelser uten å endre Champion eller bettingreglene. Kontroller i en senere, faktisk rapport om WIN-market blir lagret **før cutoff**; ikke regn gevinsten som oppnådd bare fordi kode ble endret.

Ikke sammenlikn 3/4 denne prospektive delkohorten direkte med CORE-002s 9/31 historiske løp: nevner, dato, baner og dekningsmål er forskjellige. Ingen produksjons- eller BET-endring er autorisert.
