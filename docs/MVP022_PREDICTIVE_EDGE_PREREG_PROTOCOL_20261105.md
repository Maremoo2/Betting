# MVP-022 | Forhåndsregistreringsklar protokoll – Predictive Edge Research

**Utformet:** 5. november 2026 · **Status:** `READY_FOR_OWNER_REVIEW`, ikke aktivert, ingen modelltrening eller produksjonspromotering. `bet_authority=false`.

## 1. Formål og avgrensning

Benter er primær metodisk kilde for uavhengige fundamentale sannsynligheter, sammenstilling med markedsinformasjon, kalibrering og tidsriktig verdi. Ventus er sekundær støtte for adskilte prediksjons- og beslutningslag. Ingen av metodene dokumenterer en faktisk positiv edge i våre 30 historiske løp.

**Spørsmål:** Gir en *forhåndslåst*, kun forskningsbasert prediksjonskomparator lavere multiclass log loss eller Brier enn både gjeldende fryste Champion V1.1 og normalisert fullfelts-WIN, på nøyaktig de samme framtidige fysiske løpene med samme tilgjengelige informasjonsvindu?

Champion V1.1, CORE-004, V3.3.12, grunnleggende/markedsbaserte signaler, blandingsvekter, BET/WATCH/PASS, minsteodds, staking og PIT-T−4-hardgates **endres ikke i dette oppdraget**. Forskningen har ingen autoritet til å levere p(win), bette, sette P/L eller velge et live Champion.

## 2. Retrospektivt utforskende grunnlag – LÅST, IKKE HOLDOUT

Første **30 distinkte** `TRIPLE_EVALUABLE` i kronologisk `race_start_utc`, deretter fysisk `race_id` som tiebreaker, er låst i [maskinlesbar, tidsordnet første-30-liste](MVP022_FIRST30_EXPLORATORY_SOURCE_LOCK_20261105.json). Originalt kumulativt scorecard: [CORE-003 41911371831](https://github.com/Maremoo2/Betting/actions/runs/41911371831), artefakt **13364215238**, `index.json` SHA256 `6dd2ab97bc4e2893e22836777290e9f3d985e0a88c99d5b7df57a68fa6cfa019`. En separat, fullstendig 30-raders originalbasert QA-ledger er bevart hos HQ/DEV: SHA256 `08de79b2df0ffcec10b2711e6d6661c07c03d2dbca34a389d7ac86189905c5b7`, med alle 60 independently re-hashed complete/raceday råfiler, frosne model-sha-pointers, observasjonsklokker og race-ID-er.

| Identisk utvalg, n = 30 | Log loss | Multiclass Brier |
| --- | ---: | ---: |
| Champion V1.1 | 2.1290872503 | 0.8614155898 |
| CORE-004 | 2.0876948876 | 0.8480727641 |
| Normalisert same-freeze WIN | **1.9491062640** | **0.8235196459** |

30 løp fordelt på **bare tre kalenderdatoer og seks banedager**; 19/30 løp favoriserer markedet over Champion ved log loss, 19/30 favoriserer markedet over CORE-004. På 4. november isolert var gjennomsnittlig Champion-minus-marked log loss **−0.01968** og CORE004-minus-marked **−0.05498** (modellene bedre den dagen). Dette viser at forskjellen varierer og er korrelert, og at et uavhengig statistisk intervall fra 30 enkeltløp ville være misvisende. **Ingen robust kalibrerings-, EV- eller PIT-konklusjon.** De tre senere original-triplene i samme scorecard er også resultatkjente og regnes *ikke* som fremtidig holdout.

## 3. Før start – obligatorisk eierregistrering

Det eksisterer **ingen aktiv forsøksperiode** før eier har underskrevet/merget et datert forskningsdokument og låst:
- fullstendige kode-SHA-er for Champion, CORE-004 og eventuelle forskningskomparatorer;
- modell-/markedsparametre, kildefeil- og avvisningsregler, fullfelt- og as-of-kontrakt, målingskode og evalueringstabell;
- eier-signaturtidspunkt i UTC og eksplisitt tidligste mulige start.
- ikke-betinget kandidatutvelging: **ALLE** fremtidige NO/SE-travløp i planlagt kildekø. Telle både `DISCOVERED`, `BLOCKED_SOURCE`, `NOT_EVALUABLE`, `PIT_NOT_CERTIFIED`, samt `EVALUABLE`. Ingen resultat- eller oddsbasert seleksjon.

**Tidligste anbefalte start:** første rene **mandag 9. november 2026 kl. 00:00 Europe/Oslo**, *kun dersom* eier godkjenner hele protokollen og hashlåser kode/kilder **før denne tiden**. Hvis ikke: flytt starten til første mandag kl. 00:00 Oslo som ligger **minst 24 timer etter faktisk forhåndsregistrering**. Ingen 5.–8. november-data gjøres automatisk til «prospektiv holdout» i ettertid.

**Separasjon:**
- **Utvikling / historisk:** alle resultatkjente første-30 og øvrige før signert start – kun hypoteser og diagnostikk; ikke evaluering av endret modell på samme data.
- **Prospektiv observasjons-/valideringsblokk:** de neste fire hele kalenderukene fra aktiveringsdato, låste modell- og sammenligningsregler, uten trening på egne utfall.
- **Urørt bekreftelsesholdout:** påfølgende fire hele kalenderuker, fryses som separat tidsperiode før validering begynner. Ingen oppdatering etter at første holdout-race er startet. Ved forsinket aktivering forskyves både blokker framover.
- **Replikasjon:** ytterligere, separat fremtidig periode etter owner signoff før enhver eventuell modellpromotering. Governance krever minst **500 forward races** og oppfylt P0; 30/33 er bare forskning.

Tidsvinduer er kalenderbaserte, uavhengige av spillodds, beregnet EV, vinner, antall BET eller modellens skjønn.

## 4. Kilder og observasjonskontrakt

For hvert løp arkiveres: fysisk `RIKSTOTO:<raceday>:<race>`, originalt offisielt fullt startfelt, uavhengige registrerte heste-ID-er, alle strykninger/revisjoner, original Collector-proveniens, hoved- og kilde-SHA, request-start og fetch-completed UTC, uavhengig leverandør-publish-tid når faktisk tilgjengelig, valgt frosset modell SHA og begrunnelsen for freeze-valget, same-freeze komplette WIN-odds før gjeldende konservative T−4, og postrace komplette originale resultat- og utbetalingskvitteringer.

Ingen `TMP-*`, navnelikhets-join, partiell ATG-rad, etterfølgende VIN-odds, ikke-autentisert publiseringstid, endret modell-snapshot eller `isComplete=true` uten unik vinner godtas som full kildekontrakt. Etter-start GET kan ikke sertifisere PIT. Alle blokkerte løp bevares, men ikke innrømmes resultat/frys-score.

## 5. Forhåndsdefinerte analyser

**Primær:** løp-for-løp paired forskjell i multiclass log loss og Brier på **samme identiske delutvalg**, mellom (a) Champion, (b) CORE-004 og (c) normalisert WIN. Rapporter separate antall for fundamentale fullfelt, marked, par og treveis, samt full `SOURCE_CAPTURED→VALIDATED→MODEL_ELIGIBLE→FROZEN→RESULT_VERIFIED→WIN_EVALUABLE`-trakt.

**Sekundær:** reliability bins på frosne sannsynligheter (faste 0–0.1, 0.1–0.2, 0.2–0.3, 0.3–0.5, 0.5–0.7, 0.7–1.0), med `n`, forventet andel, faktisk andel, korrelerte banedagsgrupper og eksplisitte sparsomme/ikke-estimerbare bins. Ingen claims om robust kalibrering uten tilstrekkelig uavhengige banedager og replikasjon.

**Usikkerhet:** resampling av hele **raceday/track**-klynger (fast seed `20261105` og forhåndslåst implementasjon), 10 000 replikasjoner; sensitivitetsanalyse med kalenderdato som klynge; vis antall grupper og bredde på usikkerhetsintervall. Hvis færre enn ti uavhengige banedager i blokken: kun deskriptiv presentasjon, ikke signifikans- eller superiority-krav. Seleksjonsskjevhet dokumenteres ved country, track, fullfeltstørrelse, tidsvindu, scratch og kildeårsak.

**Økonomisk separat:** EV = frossen kalibrert p × faktisk tidsriktig eksekverbar WIN-pris − 1, dokumentert omsetning/risiko, originale closing prices og resultater. Ingen EV eller CLV beregnes fra endelig payout-odds som om det var forhåndspris; ingen økonomisk EV-påstand uten faktisk registrerte eksekverbare priser og separate out-of-sample perioder. Ingen reelle spill.

**Sammenligningsfeil:** ved `model_set!=market_set`, `WIN_LATE`, `result_source_missing`, `identity_unattested` eller konflikter skal hele feilen logges. Ikke korriger historisk prediksjon. Ingen alternativ market close for å gjøre benchmark bedre.

## 6. Beslutningsgater og forbud

MVP-022 kan merkes `READY_FOR_OWNER_REVIEW` med denne protokollen. Det er **ikke** `PRE_REGISTERED`, `PROSPECTIVE_ACTIVE`, `MODEL_VALIDATED` eller `BET_AUTHORIZED` før særskilt eksplisitt eierhandling og fremtidig originalbasert QA. All model training, justering, promotering, autospill, PIT-endring, settlement- eller state-writes forbudt i dette oppdraget.

**Må signeres av eier før start:** dato/UTC, aktivert kode-/config-SHA, kandidatdefinisjon, eksakt første race-kø, valideringsperiode, holdoutperiode og akseptkriterier. Uavklarte kilder: `BLOCKED_SOURCE`.
