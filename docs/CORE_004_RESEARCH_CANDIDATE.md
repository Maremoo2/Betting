# CORE-004 – Market-free flerfaktoranalyse (forskningskandidat v0)

## Formål og status

Denne leveransen **erstatter ikke** `FUNDAMENTAL_CHAMPION_V1_1`, V3.3.12, eller eksisterende Watcher. Ingen nye modellvekter er trent, og denne kandidaten kan ikke autorisere spill, WATCH, prising, EV eller kalibreringspåstander. Alle probabiliteter er illustrerende forskningsanslag.

CORE-004 bygger en **kildedokumentert faktormatrise** for hele feltet fra den nyeste samlede, før-cutoff fundamentalkohorten. Hver hest får Champion-referansen og en separat kandidat-p(win) når hele feltet oppfyller gatekravene. Odds påvirker aldri modellens sannsynligheter. Et separat testforsøk som endrer bookmaker/tote-odds lar sannsynlighetene være uendret.

## Kildelagene som finnes nå

| Faktor | Status i CORE-004 | Kilde / forbehold |
|---|---|---|
| Livstidsstarter og seire | Scoret – frosset Champion EB-baseline | `runner_fundamental_snapshots`, fullfeltsverifisert ATG |
| Livstids andre- og tredjeplasser | Scoret – top-3 rate, EB-smoothed | Samme arkiverte kohort; ingen plass-sannsynlighetskalibrering |
| Livstidsopptjening per start | Scoret – log-transform, innen samme løp | Beløp i kildens egne enheter; **ikke sammenlign valuta på tvers av løp** |
| Erfaring: antall starter | Scoret – log-transform | Korrelert med andre faktorer; fare for dobbelttelling |
| Alder, spor, kuske-/trenernavn | Beskrivende, **ikke scoret** | Mangler dokumentert løp-/kuskefaktor og estimert effekt |
| Startmetode, distanse | Beskrivende, **ikke scoret** | Startmetode kan finnes, faktisk distanse ofte mangler |
| Siste 5 starter, form, klasse, tempo, distanse-/startmetodehistorikk og kuskeprestasjon | **Ikke tilgjengelig/verifisert** | Skal ikke gis score eller oppdiktet historikk |

## Kandidatens prespesifiserte illustrasjonsformel

Baseline `p0_i` gjenbruker **nøyaktig** `historical_win_prior` for samme kohort. For aktiv hest `i`:

- `top3_i = (wins_i + seconds_i + thirds_i + 6*(3/n)) / (starts_i + 6)`;
- `earn_i = ln(1 + lifetime_earnings_i/(starts_i+1))`;
- `experience_i = ln(1+starts_i)`;
- hver sekundær variabel sentreres, deles på løpsfeltets SD og klippes til `[-2,2]`;
- `raw_i = p0_i × exp(0.20*z_top3_i + 0.10*z_earn_i + 0.05*z_experience_i)`;
- `p_candidate_i = raw_i / Σ raw_j` over **alle aktive** hester.

Alle tre koeffisienter er **ujusterte illustrasjonsvekter, ikke trent eller validert**. Siden gevinster, plasser, opptjening og erfaring henger sammen, kan vektene dobbelttelle historisk evne. Sannsynlighetene summerer til 1 per komplett løp, men er ikke bevist kalibrerte eller bedre enn Champion. Kandidaten beregner aldri fair odds, EV, spillinnsats eller BET/WATCH/PASS.

## PIT og fullfelt-gates

- Eksisterende startliste og siste samlet `runner_fundamental_snapshots` må ha nøyaktig samme seleksjons-ID-er; duplikat, avvik i strykninger eller inaktivt felt stopper kjøringen.
- Alle aktive hester må ha kildemerket `full_field_history_complete = 1` samt gyldige starter, seire, andre-/tredjeplasser og ikke-negative opptjeningsverdier. Ufullstendige eller selvmotsigende prestasjonstall stopper hele feltet; ingen implisitt imputering.
- Observasjonstidspunkter sammenlignes som faktiske timezone-aware UTC-instanter, ikke leksikografiske ISO-strenger. Fremtidige `feature_as_of` blokkeres.
- Nyere *delvis* kohort kan ikke omgås ved å bytte til eldre komplett kohort. Bare arkiverte tidsstempler finnes; ingen uavhengig attestasjon av publiseringstid.
- `runners` / strykninger og endringer i registrert starttid mangler historisk attesterte snapshot-bevis. `roster_point_in_time_attested=false` og modellen forblir **shadow research**.

## Reproduserbar kjøring

```bash
# Egen as-of-vurdering av ett løp:
python -m hbi.core_multifactor_research \
  --db data/core003-pilot.sqlite \
  --race-id 'RIKSTOTO:S1_NR_2026-10-30:3' \
  --as-of '2026-10-30T11:53:30+00:00' \
  --out core004-race3.json

# Hele kortet, T−4 for hvert løp (historisk arkiv-replay):
python -m hbi.core_multifactor_research \
  --db data/core003-pilot.sqlite --date 2026-10-30 \
  --track Östersund --cutoff-minutes 4 --out core004-day.json
```

CLI og modell leser SQLite i `mode=ro`. Ingen database-write, nettverkstrafikk, markedsinnhenting, prod-path-endring eller automatisk betting.

## Resultat fra livearkiv 30. oktober

Analysen mot tredje CORE-003-pilot-database (GitHub workflow 41051283095) gir **3/8 forskningsklare løp** på Östersund (løp 3, 4, 5) og **35 hester med fullført faktorprofil**. Fem løp forblir blokkert, inkludert løp 6 der fullfelt-historikken ikke kan verifiseres. Løp 3: toppforskjell mot Champion er ca. +6,53 prosentpoeng på Black Adam. Dette er **kun modelluenighet**, ikke dokumentert edge eller bedre prediksjon. Hele JSON-replay ligger i utviklingsrapporten, ikke i versjonskontrollerte hendelsesdata.

## Strenge akseptansekrav før en v1-kandidat kan vurderes

1. Dokumentere og tidsstemple roster/strykninger og kildepublisering på en uavhengig måte.
2. Skaffe faktisk prestasjonsform, siste starter, løpsklasse, distanse- og kuskestatistikk med identifiserte kilder.
3. Låse datadefinisjoner, håndtere korrelasjon og estimere koeffisienter **kun på kronologisk treningsmateriale** med riktig utfall, uten odds som fundamental input.
4. Evaluere Champion mot ny kandidat på **samme** out-of-sample løp, med log loss, Brier, kalibreringskurver, block/missingness-kohorter og usikkerhetsintervaller.
5. Kreve stabil forbedring før eventuell modellpromotering. Fortsatt ingen automatisk spillbeslutning uten egen prospektiv validering og gategodkjenning.
