# Fase 2 – datagrunnlag: endelig evidensstatus

22. november 2026. Isolert forskning, NO BET. **PHASE_2_DONE = FALSE.**

PR: [Betting #214](https://github.com/Maremoo2/Betting/pull/214), stablet på den urørte PR #213-grenen, base `2511a4796e183b091ab6d5116a2a594be10fc58e`. Implementasjonen er frosset i `8cd260dc0fb9bf69c828ae8253517bafeb2e4348`; senere dokumentasjonscommit endrer ikke koden. Ingen merge, deploy, aktiv database, Sheet eller automasjon er endret.

## Faktisk implementert

1. Originalkvitteringsvalidatoren avviser ugyldig eller naivt informasjonstidspunkt kontrollert, fremfor å kaste TypeError. Inklusiv as-of-semantikk og den separate, strenge T−4-porten er bevart.
2. Eksisterende historikkdekning bevarer sport, løpstype, startmetode og distanse med kildeproveniens, uten å gjøre metadata til godkjente modellvariabler. Uattesterte cachefiler åpnes ikke bare for å bli forkastet.
3. Samme dekningskommando kan avgrenses per måned før lesing. Dette erstatter minnekrevende helarkivlesing med hashkontrollerte, avgrensede revisjoner. Ukesarkivers faktiske dato/ISO-uke kontrolleres fortsatt.
4. Den eksisterende ATG-originaladapteren fra #196 er gjeninnlemmet. #195 ble merget til main før #196 ble merget til den tidligere #195-grenen; adapteren kom derfor aldri inn i main. Resolveren leser nå det autentiske game-envelope-formatet. Eksisterende kanonisk T−4 og beslutningstid sendes separat. Ingen kilde, permanent identitet eller sannsynlighet godkjennes automatisk.

## Fem akseptansekrav

| Kriterium | Status | Autentisk resultat og konkret mangel |
|---|---|---|
| Hesteidentitet | BLOCKED | 208 race-horse-observasjoner undersøkt; 196 retrospektive provider-korroborasjoner og 12 avvisninger for monté/racemetadata. Ingen uavhengig attestert registerkobling. Monté-kravet er ikke endret. |
| Historikk | BLOCKED | 90 historikkrader, 23 mål-hest-oppføringer; 33 rader består eksisterende A/B/C, men D/E-godkjenning er 0. Dette er rader, ikke komplette hester/felt. DATA-004E: 24/24 PDF-originaler og 30/30 utvalgsrader verifisert; ingen uavhengig, akseptert 390-felts gullfasit. |
| PIT | BLOCKED | 0 PIT-godkjente hester/løp. Publiserings-/versjonstilgjengelighet, uavhengig identitet og strykningsgrunnlag er ikke fullført. Lokal SHA er ikke uavhengig tidsattestasjon. |
| Fullfelt | BLOCKED | 0 autentiske MODEL_INPUT_ELIGIBLE-felt. Kontrollfelt `RIKSTOTO:S1_NR_2026-10-21:9`: 12 hester/60 rå historikklinjer, men identitets-/historikk-/tidsbevis utilstrekkelige. Senere kilder er ikke tilbakeført. |
| Historisk dekning | BLOCKED | Stort markeds-/resultatarkiv, men 0 fullfelt med godkjente historiske features, identiteter og PIT. Ukjent startmetode er ikke imputert. |

## Historisk inventar – sammenlignbare enheter

133 månedsdeler er kontrollert med eksisterende originalbaserte revisor. Hele inventaret omfatter 202 946 fysiske referanser, hvorav 18 947 gjelder 2025 og kun brukes til kilde-/inventarmetadata. Ingen 2025-resultatfil åpnes av revisjonen.

2015–2024 har **183 999 referanser**, hvorav **183 961 har arkivert kilde** og 38 bare har metadata. Dette forklarer forskjellen fra tidligere 183 961, uten nye eller rekonstruerte løpsoriginaler. Totalt er 201 189 startfelt kildeavstemt, 159 044 markedfelt komplette og 31 789 resultater strengt verifisert. Tallene gjelder hele inventaret med land-/sportsavgrensning rapportert separat, ikke bare NO/SE-trav. 2025-resultater inngår ikke.

Den tidligere lagrede resultatmarkeringen 31 796 er ikke videreført som dagens fasit. Eksisterende originalrevalidering dokumenterer syv avvik (`outputs/P1_011_HISTORICAL_ARCHIVE_20261119/legacy_result_revalidation_differences.json`); dagens strengere kontroll gir 31 789. Originalene og historiske forventningsverdier er uendret.

NO/SE T-kodet inventar: 86 817 referanser inklusive 2025-kildemetadata, **76 705 uten 2025**. Modellklare, representative treningsfelt: **0**. Resultatetiketter alene er ikke historiske modellinput.

| År | Fysiske referanser, alle land/sporter |
|---|---:|
| 2015 | 9 197 |
| 2016 | 16 134 |
| 2017 | 17 505 |
| 2018 | 20 115 |
| 2019 | 19 895 |
| 2020 | 19 496 |
| 2021 | 20 115 |
| 2022 | 20 407 |
| 2023 | 20 468 |
| 2024 | 20 667 |

Representativitetsprotokollen ble frosset før resultatanalysen, SHA-256 `a7fa78d841393892766a7d76120666d06df4071d5248e721c08f607e1b153af1`. Dens rapporteringsminimum er ikke en ny trenings-/modellpolicy eller dokumentert statistisk styrke. Ingen modell er trent.

## Autentisk før/etter og ny kildeobservasjon

Samme 3 708 uendrede originalfiler fra desember 2015 ble kjørt med baseline og rettet kode: **1 218 løp, 1 218 kildeavstemte felt, 269 strengt verifiserte resultater og 898 komplette WIN-felt i begge tilfeller**. Identitets-, feature-, førstartmarkeds- og PIT-godkjenning er 0 før og etter. Alle opprinnelige sikkerhetsflagg er identiske. Ny diagnostikk gjør sports-/startmetodeproveniens synlig for 1 218 felt; den gjenvinner ingen tidligere prediksjon.

Et fremtidig felt ble valgt før innhenting: Umåker 1, 22. november, `S1_NR_2026-11-22:1`, ATG `2026-11-22_27_1`, ni hester. Oppgitt start 12:20 Europe/Oslo, eksisterende kanonisk T−4 12:16. Eksisterende kildeklient fullførte originalresponsen 12:04:52.960538 Europe/Oslo, SHA-256 `56a74eff51a2e6aa38329ade5da4cc99db07407d69e51f0cc69a5de6488f76fd`, med identisk gjenlesing. Kalenderoriginal SHA-256 `26faec01b5e11feb1b48e28b7f04c83308ddf3e5c28c553c26fd4a711e556a5d`.

Adapteren verifiserer ni lokale ATG-identifikatorer og livstidsstatistikk i originalen. Dette gir **ikke** uavhengig permanent identitet eller fem individuelt identifiserte tidligere starter. Kilden forblir blokkert for modellopptak. Ingen ekte p(win), nye modellfrys eller PIT-sertifikater ble produsert. Originalbytes er kun beholdt lokalt, ikke publisert i offentlig CI.

## Tester og integritet

Implementasjonscommit `8cd260d`: [CI 45015975720](https://github.com/Maremoo2/Betting/actions/runs/45015975720) **Ruff PASS, 2 295 Pytest PASS / 110 SKIP**, og alle obligatoriske originalreplay-steg PASS. Protected Strategy, Research Integrity og Provider Smoke er PASS på samme commit. Dette er teknisk CI, ikke operativ modell-/PIT-godkjenning.

Windows-kjøringen før de siste fem testtilleggene ga 2 239 PASS / 131 SKIP / 30 FAIL. Feilene er ikke kalt PASS; de gjelder eksisterende Windows-/symlink-/shell-/legacyforhold. Endelig commit og nye testresultater registreres i leveransekvitteringen og PR-en. Ingen historisk fasit eller replaykrav er fjernet.

Kanonisk modellkjerne, strategiregler, T−4-definisjon og aktiv workflow er uendret. I `cloud_run003_model.py` er bare eksisterende beregnet cutoff videresendt til resolveren. Negative tester bevarer avvisning av sene/falske/kolliderende/uattesterte bevis og null persistens ved blokkering.

## Etterprøvbar levering og nødvendig neste handling

Lokale revisjonsbevis ligger i `outputs/BETTING_PHASE_2_DATA_FOUNDATION_FINAL/`: `historical_coverage_after_summary.json`, `historical_races_after.jsonl`, `coverage-months/`, `authentic_before_after.json`, `bounded_before_after_input_hashes.json`, `authentic_identity_corroboration.json`, `authentic_history_quality.json`, `authentic_fullfield_replay.json`, `data004_original_pdf_verification.json`, `prospective_atg_source_verification.json` og `lost_adapter_rootcause.json`. De er ikke nye godkjente treningsdata.

**Neste nødvendige handling:** Skaff en autorisert originalpakke for ett fremtidig fullfelt som dokumenterer registeridentitet/kryssreferanser, komplette historikkversjoner med før-T−4-tilgjengelighet og uavhengig strykningsgrunnlag. Eksisterende kildekobling kan nå validere faktiske originaler; den kan ikke skape disse eksterne attestasjonene. DATA-004E trenger fortsatt to reelt uavhengige lesere og separat adjudikasjon. Ingen nye generelle systemer foreslås.

`CHAMPION_UNCHANGED=true`, `PREWATCH_V3_3_12_FROZEN=true`, `PIT_HARDGATES_UNCHANGED=true`, `2025_LOCKBOX_CLOSED=true`, `AUTO_BET=false`, `BET_AUTHORITY=false`, `AUTO_MERGE=false`.
