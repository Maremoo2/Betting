# Betting HQ – master-roadmap og gjennomføringsstatus


## MVP-009 – prospektiv kildeverifisering og automatisk diagnostikk (3. november 2026)

**Gjeldende operative status; eldre MVP-008-/007-/005-seksjoner nedenfor beholdes som historikk.** Frist 13. november 2026 kl. 18:00 Europe/Oslo. Verifisert baseline ved oppstart: main `71724072e8879881ecbe8201b9c8110197340aad`. PR #122 og #123 er merget; de skal ikke implementeres på nytt.

| Chunk | Faktisk levert | Verifisert original / CI | Status og neste nødvendige handling |
| --- | --- | --- | --- |
| **MVP-009/1 – Jägersro 4. november** | Identifisert fysisk løp `RIKSTOTO:S3_NR_2026-11-04:5`, planlagt 20:30 Oslo; eksisterende Collector/CORE-003-pipeline klart for sin ordinære prospektive kjøring. Førstegangs PIT krever faktisk T−4 før 20:26 dersom starttid uendret. | Svensk Travsports løpskalender og offentlige V86-listinger, men ingen innhentet og tidsattestert original svensk startnummer→profil/ATG-ID→Rikstoto-kjede for hele aktive feltet; 9 fra tredjepart er kun foreløpig nevner. | **BLOCKED_SOURCE_IDENTITY** – 0 prospektivt godkjente hester. Verifiser originale svenske startlisteprofil-ID-er, ATG horse.id og Rikstoto raw starts/scratched via planlagt Collector før as-of; ellers kandidat Halmstad 7. november (offisiell kalender bekreftes ved bruk). Ikke navnebasert EXACT. |
| **MVP-009/2 – Rikstoto scratched** | Kontrollerte originale Eskilstuna-kildene og både gammel forskningsparser og streng PIT-parser. Ingen endring i parser eller gate. | [Run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709), raw /scratched SHA-256 `1273a06752f5424480f729d256279ea649860d94ac096dcc6d4c3c42a001587a`; success=true, løp 1 ikke oppført, starts 12/12 false. | **BLOCKED_SOURCE** – mangler autoritativ kontrakt for utelatt løpsnøkkel vs null/ukjent/ikke-publisert. Behold `UNVERIFIED_SCRATCH_SOURCE` og streng `_scratch_set()`. Ingen kodeoppgave før offisielt kildebevis. |
| **MVP-009/3 – automatisert read-only beslutningsdiagnostikk** | **CODE_COMPLETE / PR OPEN, IKKE MERGET.** [PR #124](https://github.com/Maremoo2/Betting/pull/124) gjenbruker merget `hbi.mvp008_decision_audit`; ny runner verifiserer frosne rapporters SHA/løps-ID, bevarer kildeindeks/attest-SHA og skriver eksklusiv per-løpsdiagnostikk. Eksisterende planlagt CORE-003-workflow kobles til upload etter PIT-attestasjon. | [CI 41640968602](https://github.com/Maremoo2/Betting/actions/runs/41640968602) **PASS**: Ruff, 1463 passed / 74 skipped, Collector originalreplay, pluss 10/10 originale Eskilstuna-regresjoner. GitHub-artefakt `mvp009-original-decision-diagnostics-41640968602` (ID 13232354202) ble faktisk generert og lastet opp. 2/2 originale fryste løp; Eskilstuna løp 1 12/12 aktive, komplett WIN, PIT-attest matches; løp 3 mangler attestasjonskobling; 0 BET. Original modell-SHA løp 1 `4853ed6bc8c7c7063a5898f4b815e552989d29d9b3121372fd338eb0e63f9916`. | **Neste tekniske PR til eiervurdering: #124.** Samlet PR-check er IKKE helgrønn: [HBI Provider Live Smoke 41640968680](https://github.com/Maremoo2/Betting/actions/runs/41640968680) FAIL med `NO_FULL_FIELD_LIVE_PASS:FR`; [main Live Smoke 41638471333](https://github.com/Maremoo2/Betting/actions/runs/41638471333) hadde PASS ca. 18 minutter tidligere da FR Nantes-løp 3 hadde fullfeltsdekning. Dette er variabel ekstern FR-dekning, ikke en dokumentert endring i provider-koden fra PR #124; kildekontrollen kan ikke forties. Kun eier kan godkjenne merge. Prospektiv produksjon av nytt *planlagt* CORE-003-artefakt må bekreftes i en ordinær fremtidig kjøring etter eventuell merge; PR CI er ekte originalreplay, ikke framtidig PIT. |
| **MVP-009/4 – første uavhengige PIT** | Eksisterende PIT-sidecar og source-gates uendret; Eskilstuna 3/3 T−4-kilder og 1 gjennomført attestasjon er verifisert, **0 sertifisert**. | Original [run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709). | **PIT_NOT_CERTIFIED**: to konkrete gater – `STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED` og `UNVERIFIED_SCRATCH_SOURCE`. For et nytt fysisk løp kreves autoritativ fullfeltsidentitet + strykestatus, tre rå SHA, klokker før cutoff, uavhengig Collector-versjon, modellfrys og entydig attestasjonsjoin. Ingen backdating. |

**MVP-konklusjon:** Originalfangst, isolert SQLite, Champion/CORE-004 og WIN fungerer i prospektiv forskningsmodus; GitHub CI demonstrerer nå dessuten helautomatisk avledet diagnostikk fra autentiske fryste originaler på PR-HEAD. Kodeintegrasjon til planlagt forskning er **ikke på main** før eiermerget PR #124. Full PIT og kvalifisert V3.3 BET/WATCH/PASS er **ikke** levert: uavhengig identitet, autoritativ scratched-kilde og senere kalibrering/FFQ-1/preregistrert batch mangler. `bet_authority=false`. Ingen nye modeller, odds-/innsatsregler eller produksjonsstate er endret.

## MVP-008 – leveranseorientert status 3. november 2026

**Dette er gjeldende fremdriftsstatus; eldre MVP-007/MVP-005-tekst nedenfor er historisk.** Dokumentasjon endrer ikke frosne strategier eller PIT/BET-hardgates.

| Chunk | Teknisk leveranse | Bevis | Eksakt gjenværende sperre |
| --- | --- | --- | --- |
| **008A / strykekontrakt – BLOCKED_SOURCE** | Original Eskilstuna T−4-/scratched og begge eksisterende parsere revidert; source-limitation fastslått | [CORE-003 run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709), pit003a-source-receipts, original scratched.raw.json SHA-256: 1273a06752f5424480f729d256279ea649860d94ac096dcc6d4c3c42a001587a | Rikstoto svarte success=true med kun løp 2,3,4 som nøkler; løp 1 mangler. /starts rapporterer alle 12 med isScratched=false, men offisiell kontrakt for manglende løpsnøkkel kontra null/ukjent/ikke publisert ble ikke funnet. Streng _scratch_set() må fortsette å returnere unknown; eldre research _scratched_for_race() sin tom-mengde-antakelse er ikke PIT-bevis. |
| **008B / svensk identitet – BLOCKED_SOURCE_IDENTITY** | Eksakt fysisk kandidat identifisert: Jägersro 4. november kl. 20:30, RIKSTOTO:S3_NR_2026-11-04:5; offentlig forhåndsliste viser 9 hester | Offentlig V86-startliste, men ingen komplett tidsattestert original-ID-kjede bevart | 0/9 av de foreløpig oppførte er prospektivt attestert; 9 er **ikke** verifisert aktivt originalfelt. Original Sportinfo/Svensk Travsport startnummer→stabil ID, ATG horse.id og Rikstoto-kryss, rå SHA og as-of mangler. Alternativ kandidat: Halmstad 7. november (reverifiser først). |
| **008C / modell til beslutningsdiagnostikk – IMPLEMENTERT, PR OPEN** | [PR #123](https://github.com/Maremoo2/Betting/pull/123) gir read-only diagnostikk for alle aktive hester, Champion p(win), teoretisk fair odds, CORE-004 research, WIN, normalisert marked, ukalibrert teori-EV og per-hest manglende V3.3-kontrakter. Eksklusiv output, ingen BET. | PR HEAD e2aceafd5853fcda55553ea879b239791bcfc432; [CI 41637151141](https://github.com/Maremoo2/Betting/actions/runs/41637151141) Ruff PASS, 1454 PASS / 73 SKIP, autentisk Collector-arkivreplay PASS. Separat lokal kontroll mot Eskilstuna-originalmodell SHA-256 4853ed6bc8c7c7063a5898f4b815e552989d29d9b3121372fd338eb0e63f9916 viser **12/12 aktive og 12/12 WIN**, alle BLOCKED; 17 lokaltester PASS, én valgfri originalartifakt-test SKIP i vanlig CI. | Original kildeidentitet og strykestatus, PIT, kalibrerte p_low/p_mid/p_high, FFQ-1, minstepriser og preregistrert V3.3 batch er ikke tilgjengelige. V3.3-evaluering ikke kalt; PR ikke merget; bet_authority=false. |

**Eskilstuna T−4-fasit:** [run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709) fanget 3/3 originalresponser før T−4, modell og WIN 12/12. Én faktisk fangst, én vurdert attestasjon, **null sertifiserte**. De eksakte sperrene fra PIT-index er STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED og UNVERIFIED_SCRATCH_SOURCE. Grønn CI er ikke lik PIT PASS.

**Neste operative P0 handling før MVP-frist 13. november 2026 18:00 Oslo:** Sikre en offisiell, original og tidsriktig fullfelts startnummer→registrering/Sportinfo→ATG horse.id→Rikstoto-kjede og separat dokumentert scratch-kontrakt (inkludert null/ukjent/ikke publisert). Prøv Jägersro 4. nov; hvis den eksterne originalen ikke er tilgjengelig, velg Halmstad 7. nov. Tilfør ingen kode eller PASS som omgår kildesperrer. Første INDEPENDENT_PIT_CERTIFIED krever alle samtidige kilde- og modellavstemminger; verken kodeleveranse eller observasjon alene gir BET-autoritet. Eneste nye DEV-PR er #123 for diagnostikk; eieren bestemmer eventuell merge.



## MVP-007 – operativ status 3. november 2026 (oppdatert etter PR #122)

**Dette er nyeste status; eldre daterte MVP-005-/30. oktober-punkter nedenfor er historiske.** Ingen PIT-/BET-gate er endret.

- **DEV-007A: DONE / MERGED.** [PR #122](https://github.com/Maremoo2/Betting/pull/122) ble merget 2026-11-03T11:59:53Z, merge-commit `741d927e664b25e183256613c2b7c7f83d69f27d`. Eneste programvareendring er korrekt CLI-telling av `results` ved `attest` (fortsatt `records` ved `capture`), pluss seks regresjonstilfeller. [PR-CI](https://github.com/Maremoo2/Betting/actions/runs/41631306721): Ruff PASS, 1437 passed / 72 skipped, original-Collector replay PASS.
- **Eskilstuna løp 1 (2026-11-03):** [CORE-003/T−4-run 41626023709](https://github.com/Maremoo2/Betting/actions/runs/41626023709) dokumenterer 3/3 originale kilder før T−4, WIN 12/12 og begge forskningsmodeller `MODEL_READY`; én faktisk fangst og én vurdert attestasjon, **0 PIT-sertifiserte**. Kildeblokker: `STABLE_CROSS_PROVIDER_ID_NOT_ATTESTED` og `UNVERIFIED_SCRATCH_SOURCE`. Rikstoto `/scratched` manglet eksplisitt løp 1; ikke tolk dette som verifisert tom liste.
- **Neste P0-kandidat:** Jägersro 4. november 2026 løp 5 kl. 20:30 Oslo (`RIKSTOTO:S3_NR_2026-11-04:5`). Offentlige tredjepartsoversikter viser foreløpig ni hester, **ikke en attestert original fullfeltnevner**. Svensk Travsport-startliste med originale profilreferanser, rå Sportinfo/ATG/Rikstoto-identiteter, endringer/strykninger og før-as-of SHA-/klokkebevis er ennå ikke dokumentert.
- **Prioritert handling:** Fullfør originalbasert, tidsriktig identitet for samtlige aktive hester; dokumenter offisiell semantikk for manglende løpsnøkkel i `/scratched`; kjør eksisterende strenge PIT-attestasjon uten backdating eller endrede hardgates. Hvis bevis mangler: `BLOCKED_SOURCE_IDENTITY` / `PIT_NOT_CERTIFIED`, aldri falsk `PASS`.
- **Teknisk MVP-beslutning:** 13. november 2026 kl. 18:00 Oslo. Prospektiv forskningskjede demonstrert, men uavhengig identitet, strykestatus og PIT fortsatt ikke godkjent; `bet_authority=false`. Ingen ny kodeoppgave uten en konkret kildebevist implementerbar feil.

## MVP-005 – gjeldende styring og MVP-kritisk sti (3. november 2026)

**Dette er den gjeldende beslutningen for neste steg og erstatter tidligere administrative reviewkrav i eldre, daterte avsnitt nedenfor.** Prosjekteieren er eneste autoriserte mergebeslutter. Ekstern godkjenner, `HQ_REVIEWER_LOGINS`, `APPROVED_FOR_MERGE`-kommentar og obligatorisk branch protection er **ikke** lenger krav. Ingen merge uten uttrykkelig tillatelse fra eieren. Full teknisk kildeintegritet, originale hash-bevis og alle PIT/BET-hardgates beholdes.

### Oppnådd mot MVP

- **MVP-INTEGRATION-003:** Autentisert Collector-original → kildehash-verifisert SQLite med unike per-løp-poster, readback og idempotens; `TMP` og manglende uavhengig identitet gir fortsatt streng modell-/PIT/BET-blokkering.
- **MVP-INTEGRATION-004:** Ekte, historisk Halmstad løp 10 (2. november) har importert original PDF og `/starts`, vurdert 8/8 entydige ATG-navn/startnummer og kjørt uendrede Champion/CORE-004 på nytt fra isolert SQLite. Begge p(win)-summer er `1.0`, `MODEL_READY`, `HISTORICAL_REPLAY`, `research_model_eligible=true` og `independent_identity_attested=false`. `pit_certified=false`, `bet_authority=false`. Bevis: https://github.com/Maremoo2/Betting/actions/runs/41605276615 og immutable `mvp004-historical-research-41605276615`-artefakt.
- Teknisk CI på den historisk beståtte PR-HEAD `0a629a8d794af5c1a1d68e68ede14aa68990e59e`: Ruff PASS, 1 431 tester PASS / 72 SKIP; `v1-integrity` PASS; `protected-strategy` PASS. **Dette må bekreftes på ny HEAD etter administrative dokument-/workflowendringer.**
- Uavhengig GitHub-review var en **administrativ** rød gate. Den er ikke lenger et gjeldende akseptkrav etter eiers beslutning. Dansk `NO_FULL_FIELD_LIVE_PASS:DK` forblir rød, og danske løp var ikke faktisk forsøkt i sammenlignede live-smoke-kjøringer; ingen dansk datadekning er påvist. Denne separate diagnostikken er ikke automatisk Collector-mergeblokker uten et uttrykkelig DK-dekningskrav.

### Datoer, eierskap og aksept

| Frist (Europe/Oslo) | Leveranse | Status / aksept |
| --- | --- | --- |
| **4. november 2026** | PR #121: fjern administrativ HQ-gate, oppdater roadmap, verifiser **ny eksakt HEAD**, CI, kildeintegritet og uendret PIT/BET-kontrakt | DEV leverer bevis; eieren avgjør merge |
| **6. november 2026** | Betinget merge til `main` | **Kun ved uttrykkelig eiersamtykke**, PASS på relevante automatiske tekniske kontroller, ingen sikkerhetsregresjon; ellers `BLOCKED` |
| **10. november 2026** | Første egnete prospektive norske/svenske løp med autentisert Collector-original og fullt ATG-felt | Etter eventuell merge: verifiser fysisk løp, hester, strykninger, kildeversjon og originaler før modell `as-of`; kjør uendrede modeller; attester T−4 uavhengig; rapporter `PASS`, `BLOCKED` eller `NOT_OBSERVED` |
| **13. november 2026 kl. 18:00** | Teknisk MVP-beslutning | Fungerende prospektiv kjede og faktisk PIT-evidens, eller konkret dokumentert `BLOCKED` med første feil/observasjonsmangel. **Ingen BET-autoritet automatisk.** |

### Roller og beslutningsregler

- **Roadmap/HQ:** undersøk nøyaktig PR-head og alle statuskontroller; klassifiser tekniske feil kontra separat leverandørdekning; hold kritisk sti og datert bevis oversikt. Ikke opprett nye prosesser eller sideprosjekter.
- **Betting DEV:** bare nødvendige feilrettinger når konkrete tekniske blokkeringer er bevist. Ingen ny modell, ny arkitektur, endring i Champion/CORE-004/V3.3.12, innsatsregler eller hardgates.
- **Prosjekteier:** autoriser merge etter faktisk teknisk aksept. Branch protection/ruleset er frivillig. Det kreves ingen andre menneskelige reviewers.
- **Prospektiv PIT:** Collector-morgenprogram (planlagt kl. 07:00) er ikke alene T−4-bevis. GitHub cron kan være forsinket; observer faktiske kildeklokker. Ingen historisk replay eller syntetisk attest gir prospektiv sertifisering.
- **Risiko:** Høy for 13. november: prospektiv T−4-innsamling, ekte versjons- og publiseringsbevis og ATG-dekning er ikke bevist som ferdig. Hvis observert men utilstrekkelig, bruk `BLOCKED`; hvis ikke observert, bruk `NOT_OBSERVED`. Ikke erstatt med teoretisk grønn status.

**PR under arbeid:** https://github.com/Maremoo2/Betting/pull/121. **Denne roadmap-oppdateringen autoriserer ikke merge, autospill, workflow-dispatch eller bet.**

---

### Historisk roadmap (30. oktober; eldre administrative reviewkrav er foreldet)

**Rapportdato:** 30.10.2026 · **Modus:** GITHUB_REVIEW_AND_SOURCE_EVIDENCE_ONLY · **Betting:** OFF/ikke autorisert.

Dette er én samlet oversikt over oppnådd **kodeleveranse** versus faktisk **funksjonell akseptanse**. En merget PR, grønn GitHub Actions-kjøring eller simulatorresultat gir aldri i seg selv produsert PIT-bevis, kalibrert modelledge, gyldig oppgjør eller BET-mandat.

> **Oppdatering 30.10, senere kildekontroll:** [PR #92](https://github.com/Maremoo2/Betting/pull/92) har full CI PASS (**1167 pass / 47 skip**) og offisielt start-/strykningsbevis [run 41123773696](https://github.com/Maremoo2/Betting/actions/runs/41123773696). Alle fire Rikstoto GETs er HTTP 200; #8 finnes én gang blant 12 startlisterader, `isScratched=false`, og er **ikke på strykningslisten**. Resultatet forblir `place=0`/`kmTime="0,0"`; **start i selve løpet og gyldig tap er fortsatt ikke sikkert attestert**, ingen -25 NOK bokføring. [PR #93](https://github.com/Maremoo2/Betting/pull/93) stopper tilsvarende *forskningsmodell*-tidslekkasje i CORE-004; [pinned E2E 41124166985](https://github.com/Maremoo2/Betting/actions/runs/41124166985) PASS, mens ekstern Provider Live Smoke rapporterer selvstendig kildeblokkering. **PR #91/#92/#93 ikke merget på tidspunktet for denne oppdateringen.**


## Oversikt

| ID | Arbeidsstrøm | Kode integrert på main | Virkelig testet | Funksjonell milepæl | Neste obligatoriske akseptanse |
| --- | --- | --- | --- | --- | --- |
| **CORE-001** | Enkeltløp fullt felt | JA (#72, #80) | Fullfelt-, odds- og historiesjekker i isolert prøve | **BLOCKED** | Minst ett uavhengig PIT-attestert fysisk løp med publiserings- og klokkehistorikk og riktig originalt aktivt felt; [#89](https://github.com/Maremoo2/Betting/issues/89) |
| **CORE-002** | Hele racedays | JA (#72/#73/#80) | 9/31 eldre dag, 108/15 råkildeklar, **0/108 PIT** i arkivdelmengde | **BLOCKED** | Prospektiv race-day nevner, alle løp per land/bane, kildemangel og terminalstatus, uten etterpåklokskap; [#89](https://github.com/Maremoo2/Betting/issues/89) |
| **CORE-003** | Prefetch, identitet, historikk, T−4 | JA (#75–77, #80) | Shadow-piloter og original SQLite/kildehash. **Romme løp 8 30.10: 29 min klokkekonflikt**, post-ATG-start WIN-pris | **SHADOW, IKKE PIT-GODKJENT** | [PR #87](https://github.com/Maremoo2/Betting/pull/87) retter og [arkiv-E2E 41123151739](https://github.com/Maremoo2/Betting/actions/runs/41123151739) beviser **1/6→0/6** konservativt; review/merge, immutable rosterrevisjoner og kildens publiseringstid; [#83](https://github.com/Maremoo2/Betting/issues/83) |
| **CORE-004** | Multifaktor treningsgrunnlag | Research stub MERGET (#78) | Source-gate og syntetiske tester | **UFITTET, IKKE VALIDERT** | Verifiser last-five/klasse/kusk/distanse, tidsriktig markedsløs lineage; tren kun PIT-kronologisk uten OOS-lekkasje; [#90](https://github.com/Maremoo2/Betting/issues/90) |
| **P0-REPLAY-ENG** | Reproduserbar arkivreplay | MERGET #84/#85 | **REAL HASH-PINNED CLI PASS** [41116541999](https://github.com/Maremoo2/Betting/actions/runs/41116541999); **732 beslutninger, 321 WIN checks, 5/5 originalkilder** | **TEKNISK EVIDENS FULLFØRT** | [PR #86](https://github.com/Maremoo2/Betting/pull/86) review/merge av ikke-skriving workflow. Full kanonisk V1 audit fortsatt FAIL |
| **P0-REPLAY-INTEGRITY** | Historisk V1 replay | Diagnostikk MERGET | 305 combined replays, **5 mismatch** / 426 skip på separat auditstate | **FAIL/BLOCKED** | Uavhengig kildeadjudikasjon, godkjent append-only avklaring, aldri omskriv frosset proveniens eller gjør unntak i V1; [#81](https://github.com/Maremoo2/Betting/issues/81) |
| **P0-SETTLEMENT-SOURCE** | Skive 14.10 originalt resultat | Research-only source probe [PR #88](https://github.com/Maremoo2/Betting/pull/88) i REVIEW | **OFFISIELLE 2×HTTP 200** [41123021265](https://github.com/Maremoo2/Betting/actions/runs/41123021265), kildehash. Winner **#5**, Dividends **6,28**, valgt #8 med `place=0`, `kmTime="0,0"`, odds 31 | **ORIGINAL KILDE INNHENTET, DELTAKELSE BLOKKERT** | Primær/autoriserbar tolkning av #8 sin start-/stryk-/tapstatus og isolert regnskapsreplay; ingen -25 NOK nå; [#82](https://github.com/Maremoo2/Betting/issues/82) |
| **P0-SETTLEMENT-INTEGRITY** | Gyldig Shadow-bokføring | Original rutine finnes | Historisk åpen paper-kupong, **0** bokførte settlement-resultater for den | **FAIL/BLOCKED** | Original deltakelsesbevis, komplett resultat+dividende, korrekt idempotent replay, separat godkjent state write; [#82](https://github.com/Maremoo2/Betting/issues/82) |
| **P1** | Prospektiv markedsbaseline & kalibrering | Research-gate MERGET #80 | Eldre **297** retrospektive løp, combined minus market log-loss ca. **+0,0503** (svakere); ikke OOS | **NOT VALIDATED** | Godkjent og forhåndslåst framtidig par-design, minst 30 framtidige dager og statistisk testdesign, separat prediksjon/EV; [#90](https://github.com/Maremoo2/Betting/issues/90) |
| **OPERATIONAL** | Champion, BET, stakes | Frosset V3.3.12 | Kildestyrt Shadow/Pre-Watch, **ingen real-money tilstandsgodkjenning** | **OFF / IKKE AUTORISERT** | Alle hardgates + *separat* HQ betting-autorisasjon, aldri automatisk av kode-merge |

## Det som faktisk er fullført

- **#80, #84, #85** merget til main. Full repository PR #85-CI **1 150 PASS/47 SKIP** (ikke samtlige 1 197 testet).
- **P0 arkivbevis** med to låste originalhasher og faktisk GH-run; kilde SQLite uendret. Canonical runtime V1 **FAIL** selv om fem historiske originalkilder er rekonstruert. [PR #86](https://github.com/Maremoo2/Betting/pull/86) er review-only, ikke merget.
- **CORE-003 falsk positiv** er funnet i *samme opprinnelige seksløpsutvalg* og fjernet i PR #87, med uavhengig arkiv-GitHub-rerun [41123151739](https://github.com/Maremoo2/Betting/actions/runs/41123151739). 0/6 er en korrekt ærlig kontroll, ikke modellfeilretting.
- **P0 danske originalresultater** (HTTP 200 / response SHA-256) er hentet på GitHub runner, men hest #8 sin `place=0` og `kmTime=0,0` er *ikke* dokumentert som gyldig tapende deltaker. [#88](https://github.com/Maremoo2/Betting/pull/88) rapporterer BLOCKED selv om vinnerdividende er bevist.

## Kritisk sti for å fullføre *alle* funksjonelle milepæler

```text
P0 originalsettlement ─→ dokumentert #8-deltakelse ─→ isolert replay ─→ HQ state-approval
P0 legacy replay ─────→ kildeadjudikasjon ─→ immutable annotasjon ─→ canonical audit
CORE-003 PIT ─────────→ source clocks/roster/published-at ─→ CORE-001 PIT single race
                                                └──────────→ CORE-002 full racing days
CORE-001/002 PIT data ─→ CORE-004 feature lineage/training ─→ P1 preregistered OOS
[P0 clean + P1 proven] ─→ separat HQ-/risiko-/bettinggjennomgang; *ingen automatisk BET*
```

### Nå (kan utføres på ekte allerede)
1. Få #86, #87 og #88 gjennom nøyaktig GitHub-CI, uavhengig review og eksplisitt HEAD-bundet merge-godkjenning; ingen agent-merge.
2. Korriger **kildeklokkene i forskningsmetrikken**; skaff originalt ikke-prisbasert bevis for start-/strykestatus til Skive #8, og test idempotent oppgjør isolert uten skriverett.
3. Undersøk `LETROT_FULL_FIELD_CORROBORATION_FAILED` og `NO_PROVIDER_RACE` med original race-id/clock, og dokumenter dekning per land/dag, ikke ved å slakke på gates.
4. Gjennomfør *source lineage* og data-minimum for CORE-004 uten å trene eller evaluere på feilaktige T−4-felter.

### Senere (kan **ikke** løses sannferdig i ett møte)
1. PIT-publisering og versjonert startlistehistorikk må faktisk oppstå **før framtidige løp**.
2. Et prospektivt P1-eksperiment krever forhåndsgodkjent protokoll og nye kronologiske resultater over minst 30 dager. Dagens gamle resultater kan aldri gjøres til urørt OOS i ettertid.
3. Ingen BET eller kapitalinnsats før uavhengig P0-validering, kalibrering og separat godkjenning.

## Kilde- og tillatelsesgrense

**Original source:** GitHub Actions artifact/hash/SQLite og originale `RikstotoClient` HTTP response SHA. **Vår tolkning:** T−4-guard, kombinasjonsmodell, prospektiv kontrakt – forskningshypoteser, ikke garantert utbytte. **Brukerens egne prospektive resultater:** ikke tilgjengelige som kalibrert ROI-bevis.

`docs/DEV_WORKFLOW.md` krever eksakt PR-HEAD/HQ-review før merge; arbeidslisten gir ikke agenten merge-, scheduler- eller bet-autorisasjon. Originale gamle beslutninger og grunnkilden skal forbli uendret.

## 30.10 – korrigert fysisk løpsnevner (PR #99)

Den første heldagsrapporten ble beskrevet som 169 *fysiske* travløp, men den arkiverte kilden inneholder 15 `X1`-referanser over flere baner og 8 `S5`-referanser med `Solvalla/Bergsåker`. [PR #99](https://github.com/Maremoo2/Betting/pull/99) og original [GitHub-arkivkjøring 41127284420](https://github.com/Maremoo2/Betting/actions/runs/41127284420) skiller **169 database-referanser** fra **146 enkeltbane-kandidater** og **23 uavklarte kombinasjons-/lokasjonsreferanser**. Ingen av 146 er foreløpig individuelt sertifisert som unik fysisk start. De 23 beholdes synlige for kildekobling, ikke fjernet. Tidligere 17 foreløpig kildeklare og 0 PIT sertifiserte gjelder **alle 169 database-referanser**, ikke en godkjent fysisk løpsdekning.

## 30.10 – neste parallelle DEV-bølge (#94 og #95)

**CORE-003 heldagsdekning [PR #94](https://github.com/Maremoo2/Betting/pull/94)** – [faktisk GitHub archive-E2E 41125229029](https://github.com/Maremoo2/Betting/actions/runs/41125229029), JSON-artifact **13010796270**, SHA-256 `33febe452c4f8275507fd92106d5ef812ffb1bf2782a70bb62045e2b7e418823`, med opprinnelig HBI SQLite SHA-256 `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0`. **169** distinkte *arkiverte travløpsreferanser*, ikke verifisert fysiske løp (**146** enkeltbane-kandidater, **23** kombinerte/uavklarte), 27.–30.10, **167** etter T−4, **2** framtidige, **17** konservativt råkildeklare, **150** blokkert, **16** tidsavvik, **0 PIT-attesterte**. Første versjon Ruff F401 (ubrukt testimport), rettet; full re-run CI må kontrolleres særskilt. Det er **ikke** den samme kohorten som eldre 108-løpsaudit, så 17 mot 15 er ikke dokumentert dekningstrend.

| Land / status | Alle | Råkildeklare | Blokkert | Før T−4 |
| --- | ---: | ---: | ---: | ---: |
| Sverige | 77 | 17 | 60 | 0 |
| Norge | 24 | 0 | 24 | 0 |
| Danmark | 17 | 0 | 17 | 0 |
| Frankrike | 32 | 0 | 30 | 2 |
| Tyskland | 4 | 0 | 4 | 0 |
| Land ikke normalisert | 15 | 0 | 15 | 0 |
| **Sum** | **169** | **17** | **150** | **2** |

Diagnostiske hovedblokker (kan opptre samtidig): `NO_PRE_CUTOFF_RIKSTOTO_STARTS=118`, `NO_PRE_DB_T4_ATG_CLOCK_SOURCE=116`, `NO_RECONSTRUCTED_ACTIVE_FIELD=121`, `INCOMPLETE_FUNDAMENTAL_ASOF_FIELD=24`, `ATG_FULL_FIELD_GATE_NOT_PASSED=23`. Beste konkrete videre arbeid: original tidsriktig startliste, stabilt fullfelt og mapping av 15 UNKNOWN-country før noen modelltrening.

**P1 forhåndslåst kohort [PR #95](https://github.com/Maremoo2/Betting/pull/95)** – separate kilde-/protokoll-/fullfeltkontrakter med SHA-256, ikke-ettervalgbare løp, test for sene odds og etterregistrerte løp, parvis log loss/Brier for marked/Champion/CORE-004. **Ikke prospektivt evaluert** og ingen original GitHub-ekstern registreringsattest: alle aggregater merkes eksplisitt `EXPLORATORY_CLAIMS_ONLY_UNATTESTED` og `p1_validated=false`. Nye 30+ dager og reell tidsriktig originalkilde er fortsatt harde porter.

### Neste aksepterte utviklingsmål
- [ ] Review/merge #91/#92/#93/#94/#95 med **separat eksakt HEAD-bundet HQ-godkjenning**; ikke agent-merge.
- [ ] Øk andel tidsriktige originalkilder på hele løpsdager og bevis uforanderlig `source_published_at`, original startliste og scratchrevisjoner; 0 PIT-attestasjoner i faktisk 169-referansers arkiv.
- [ ] P0 original resultatkode `place=0`/`kmTime=0,0` for Skive #8 må tolkes av offisiell kontrakt før selv et **papir**-tap kan bokføres.
- [ ] CORE-004 market-free kildefaktorgrunnlag og forhåndsregistrering, deretter **nye** kronologiske OOS-dager. Fremtidig ytelse/profit kan ikke konstrueres fra fortid.

