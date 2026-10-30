# Betting – prioritert roadmap (revidert 30.10.2026)

> **Autoritet og datagrunnlag:** GitHub `main` ved commit `78747aaaf69c5c597ddaae5e72b4fa509de5714b`; CI, V1-systemaudit og isolerte CORE-003-pilotrapporter 30.10.2026. Dette er en **status- og prioriteringsplan**, ikke strategi-, modell-, workflow- eller BET-godkjenning. Den tidligere versjonen beskrev kun lokal CORE-001/002-utvikling og er foreldet. Alle historiske tall nedenfor er avgrenset til oppgitt kohort og tid.

## Statusdefinisjoner

- **INTEGRERT:** kode er merget til `main`; innebærer verken driftseffekt eller kvalitet.
- **TESTET:** målrettede/CI-tester er kjørt; hoppede arkivtester er ikke beståtte tester.
- **SHADOW-OPERATIV:** faktisk kilde-/forskningskjøring med artefakt. Ikke aktiv V3.3-/Pre-Watch-BET.
- **VALIDERT:** separate P0-integritetskrav og forhåndsregistrert prospektiv/OOS-evaluering er oppfylt.
- **BLOKKERT:** hard gate feiler eller påkrevd kildebevis mangler. Grønn generell CI overstyrer ikke blokkering.

## Verifisert status / ikke ferdig

| Leveranse | Integrert/operativ status | Dokumentert utfall | Åpen gate |
| --- | --- | --- | --- |
| CORE-001 ett fullfeltløp | **INTEGRERT, forsknings-CLI** via [PR #72](https://github.com/Maremoo2/Betting/pull/72) | Historisk, read-only fullfeltanalyse på kvalifisert data | Ikke bevis for full dekning eller operativ V3.3 |
| CORE-002 heldagsmotor | **INTEGRERT** via #72/#73 | 28.10: **9/31** travløp analysert; **93/201** kjente aktive hester fikk smal p(win)-baseline | Historiske T−4-hull kan ikke tilbakefylles |
| CORE-003 kildekø og Shadow-pilot | **INTEGRERT, ISOLERT SHADOW-OPERATIV** via [#72](https://github.com/Maremoo2/Betting/pull/72), [#75](https://github.com/Maremoo2/Betting/pull/75), [#76](https://github.com/Maremoo2/Betting/pull/76), [#77](https://github.com/Maremoo2/Betting/pull/77) | Første pilot 30.10 Östersund: 4 startlister, 35/50 aktive hester med verifisert historikk, 3/4 komplette historikkfelt, 0/4 komplette WIN-markeder. Senere separat [kjøring 41056206740](https://github.com/Maremoo2/Betting/actions/runs/41056206740): delta +1 komplett kildelag, +14 verifiserte hester og +1 komplett WIN-marked i rapportert kohort | Ikke bevis for generell T−4-dekning eller tidsattestert muterbar roster; ingen driftsoverføring til Watcher |
| CORE-004 flerfaktorkandidat v0 | **INTEGRERT, IKKE TRENT/VALIDERT** via [#78](https://github.com/Maremoo2/Betting/pull/78) | Östersund forskningsreplay: 3/8 løp, 35 aktive hester med kandidat-p(win); scorer livstids seire, top-3, opptjening og starter med illustrative koeffisienter | Siste starter, klasse, distanse, kusk, spor og effekter er ikke estimert; roster PIT mangler; ikke EV/BET |
| GitHub CI på siste `main` | **TESTET** | [Kjøring 41055513747](https://github.com/Maremoo2/Betting/actions/runs/41055513747): Ruff grønn, **1023 passed / 45 skipped** | CI er ikke V1 integritets- eller modellvalidering |
| HBI V1 P0-integritet | **BLOKKERT** | [Systemaudit 41055513773](https://github.com/Maremoo2/Betting/actions/runs/41055513773): temporal PASS (24 772 rader); provider WARN (718 beslutninger); runtime replay FAIL (5/297, 421 ikke replayet); settlement FAIL (1 forsinket Shadow-kupong, 728 kontrollerte poster) | Ekte P0 FAIL kan ikke endres med kosmetisk rapportering |
| V3.3.12 og aktiv Betting V3.3 | **UENDRET / SEPARAT** | [Betting-kontrakten](BETTING_V3_3.md) fordrer market-free fullfelt, kalibrerte intervaller og FFQ-1; HBI Shadow-kandidat er ikke autorisert input til automatisk BET | Ingen kalibrert operativ spillmodell og ingen real-money execution |

De tidligere **22/31** blokkerte historiske løpene 28.10 hadde overlappende innsamlingshull: startlisteforespørsel manglet for 11 løp og var først etter T−4 for 7; historikkforespørsel manglet for 11 og var først etter T−4 for 8; 2 tidlige historikkilder var ufullstendig verifisert. Summene skal ikke adderes som disjunkte løp. Rapporter baseline og nye pilotkohorter separat.

## P0-A — Integritetskjeden før ny modellpromotering (NESTE OPPGAVE)

### P0-REPLAY-001 — Diagnostiser og adjudiser fem eldre frozen-proveniensavvik

**Evidens:** [DATA-005T / PR #67](https://github.com/Maremoo2/Betting/pull/67) er allerede merget. Uavhengig arkivkontroll viste fem historiske tilfeller der vedheftede `decision_provenance.market_odds_json` avvek fra beslutningens kilde-/markedssnapshot; proveniens ble registrert 6–12 minutter senere. PR #67 stopper **nye** feilaktige vedheftinger, men endrer ikke gamle beslutninger eller proveniens. Siste audit: fem `combined_probability_mismatch` + `conflict_score_mismatch`, **297** replays og **421 skips**.

**Berørte race-ID-er (fra [audit 41055513773](https://github.com/Maremoo2/Betting/actions/runs/41055513773)):**
- `RIKSTOTO:S2_NR_2026-10-09:5`
- `RIKSTOTO:MO_NR_2026-10-17:10`
- `RIKSTOTO:S4_NR_2026-10-21:9`
- `RIKSTOTO:S2_NR_2026-10-22:5`
- `RIKSTOTO:S3_NR_2026-10-25:11`

**Arbeid:** Reproduser hver mismatch fra nøyaktig arkivert originalbeslutning, `market_probabilities_json`, referert `provider_market` og tidsstemplet proveniens. Dokumenter kolonner, nøkler, kilde-/blobhash, `created_at`, `source_observed_at`, årsak og presis forventet/observert differanse per beslutning. Kontroller negative tilfeller: senere odds, feil hest/møtenøkkel, ufullstendig felt og future timestamp. Kjør mot read-only kopi av arkiv, ikke live-kanonisk SQLite.

**Ferdigkriterium:** Alle fem klassifisert med originalbevis, enhver eventuell utbedring godkjent under append-only audit/sporbar originalrekonstruksjon, ingen fortielse av mislighold, ingen endring av frozen p(win)/policy/utfall og nye prospektive beslutninger testet mot #67-gaten. **Replay-paritet må forbli FAIL/BLOCKED for legacy-bevis som ikke kan reproduseres; ikke oppnå falsk PASS ved å øke toleranse, slette/skippe mismatch eller omskrive historikk.** Et separat, dokumentert prospektivt PASS kan rapporteres, men erstatter ikke total V1-P0 PASS.

### P0-SETTLEMENT-001 — Revider én overfrists Shadow-kupong

**Evidens:** [Systemaudit 41055513773](https://github.com/Maremoo2/Betting/actions/runs/41055513773) flagger ticket `a55a504a-bc34-487d-aced-75326dcb2b59`, `official_outcome_exists_but_ticket_unsettled_after_grace`. Samme kjørings **read-only operations report** identifiserer `RIKSTOTO:S4_NR_2026-10-14:6` (**Danmark, løp 6, 14.10**), produkt `V`, valgt `#8`, lagret `official_winner=#5`, `status=SHADOW_BET`, og `outcome_present=true`. Dette gir **indikasjon på tapende kupong, ikke bevist oppgjørsrett**: `nightly.settle_open_shadow_tickets` krever blant annet `isComplete=true`, eksplisitt sluttplassering eller dokumentert `Dsk`, og verifisert utbetaling til vinner før tap kan bokføres med `gross=0`. Loggen dokumenterer ikke om alle disse kriteriene er oppfylt. Dette er **ikke** den tidligere oktoberkupongen dokumentert i `docs/OCTOBER_OPERATIONS_2026.md`; ikke anta samme rotårsak.

**Arbeid:** Les original kupong/seleksjon, status, offisielt helt resultat, eventuell divisor og kildeproveniens. Reproduser eksisterende `settlement_integrity`/oppgjørslogikk på isolert state-kopi. Hvis nødvendig, foreslå minimal fremoverrettet korrektur med negative tester for strykning, uoffisielt utfall og ukjent gevinst. Ikke sett tvetydige tap til 0 eller endre frozen paper-P/L uten primærbevis og separat godkjenning.

**Ferdigkriterium:** Enten korrekt sporbart oppgjør med ny integritetskontroll, eller eksplisitt fortsatt BLOCKED. Utfallet må fremgå av ekte arkiv/E2E-rapport, ikke bare syntetisk pytest.

### P0-A felles release gate

Krev reelt `HBI V1 System Audit`-resultat og etterprøv alle fire P0-kontroller; provider WARN og manglende originaldata teller som åpne forhold. Ikke jobb videre med Champion-promotion, staking eller operative BET-terskler mens harde P0-feil består. Prosjektets seneste `CI SUCCESS` er ikke aksept for P0-integritet.

## P0-B — Kildedekning og PIT for kommende løp

**Mål:** Mål prospektivt for hver fysisk løps-ID fra faktisk arkiv: kildeobservert før T−4, startliste/strykninger med mutasjonshistorikk, identitet alle aktive hester, komplette fundamentals, WIN-kohort og tydelig cutoff. Skille `NOOP`, `CAPTURED_UNVERIFIED`, `BELOW_THRESHOLD`, `BLOCKED` og faktisk `FULLY_ASSESSED`. Kildedata etter cutoff kan ikke flyttes bakover.

**Tiltak:** Fortsett isolert CORE-003 Shadow-workflow, auditer rapport- og state-artefakter over flere hele dager, mål disjunkt dekningsfrafall og årsaker (bl.a. `LIFETIME_BELOW_YEAR_TOTALS`). Vurder source-aware polling, tidsstemplede immutable roster/scratch-snapshots og verifisert WIN-ferskhet uten å endre produksjons- eller V3.3.12-plan. Kildene fra [DATA-005Z / PR #74](https://github.com/Maremoo2/Betting/pull/74) er fortsatt forskningsmetadata: **120 formrader / 24 uattesterte kandidatidentiteter**, ikke produksjonsfaktorer.

**Ferdigkriterium:** Uavhengig audit per løpsdag, ingen PIT-brudd, målbar T−4-gevinst på en sammenlignbar prospektiv kohort; rapporter numerator/denominator samt feil og timerange. Ingen automatisk dataoverføring fra `core003-pilot-state` til `hbi-state` uten ny godkjenning.

## P1 — CORE-004 faktisk flerfaktor og prediksjonsvaliditet

1. Fremskaff eksakte før-start, identitetsverifiserte siste starter/form (inkl. galopp/diskvalifikasjon), startmetode/distanse, spor, kusk/trener og klasse fra tillatte kilder. Ukjent = mangler, ikke imputert.
2. Fastlås definisjoner, tren koeffisienter kronologisk og revider collinearitet; dagens illustrative vekter er **ikke** lærte effekter.
3. Sammenlign mot **samme** frozen Champion og market-only på identiske untouched OOS løp; log loss, Brier, kalibrering, fullfeltdekning og usikkerhet. Ikke bruk historiske discovery-løp som promoteringstest.
4. Først etter statistisk og operativ validitet: separat fullfelt market-free intervallmodell, FFQ-1, faktisk pris/EV og eventuelt operativ Shadow-overgang etter HQ-gate. Real-money execution forblir **OFF**.

## Plattform- og driftsporter

[DEV_WORKFLOW](DEV_WORKFLOW.md) gjelder i tillegg: M1 krever minst 14 dager Shadow parallelt og >=95 % sporbare terminalstatuser blant kildegyldige løp; M2 forhåndsregistrert PIT/OOS og aktuelle P0 PASS; M3 minst 30 dager overvåket drift, >=98 % verifiserte materielle jobber, alarmer, fallback og eksplisitt HQ go/no-go. Tidsforløp alene lukker ingen port.

Separat vedlikehold som **ikke** skal forveksles med CORE-completion:
- [Betting issue #46](https://github.com/Maremoo2/Betting/issues/46): Pre-Watch persistence/readback og heldagsdiagnostikk, åpen ved denne statuskontrollen.
- [Collector issue #20](https://github.com/Maremoo2/rikstoto-program-collector/issues/20): kalenderoppdagelse, åpen ved denne statuskontrollen.
- Collector kildeproveniens #23/#24 er merget med tester; ikke dokumentasjon på faktisk A-WATCH→WIN→BET-kjede.

## Neste beslutning / arbeidsrekkefølge

**Nå:** P0-REPLAY-001 (historiske fem, og reell framtidig proveniensparitet) + P0-SETTLEMENT-001 på samme arkivgrunnlag. **Deretter:** CORE-003 T−4-dagdekning og faktisk PIT-roster. **Til slutt:** datadrevet CORE-004-v1 og statistisk prospektiv kontroll. Ingen nye løsrevne kodepakker; en avgrenset integrasjons-PR per funn, godkjent mot eksakt HEAD. Ingen merge/auto-bet i dette roadmap-oppdraget.
