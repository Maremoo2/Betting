# Betting HQ – master-roadmap og gjennomføringsstatus

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

## 30.10 – neste parallelle DEV-bølge (#94 og #95)

**CORE-003 heldagsdekning [PR #94](https://github.com/Maremoo2/Betting/pull/94)** – [faktisk GitHub archive-E2E 41125229029](https://github.com/Maremoo2/Betting/actions/runs/41125229029), JSON-artifact **13010796270**, SHA-256 `33febe452c4f8275507fd92106d5ef812ffb1bf2782a70bb62045e2b7e418823`, med opprinnelig HBI SQLite SHA-256 `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0`. **169** distinkte travløp på alle registrerte land/baner 27.–30.10, **167** etter T−4, **2** framtidige, **17** konservativt råkildeklare, **150** blokkert, **16** tidsavvik, **0 PIT-attesterte**. Første versjon Ruff F401 (ubrukt testimport), rettet; full re-run CI må kontrolleres særskilt. Det er **ikke** den samme kohorten som eldre 108-løpsaudit, så 17 mot 15 er ikke dokumentert dekningstrend.

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
- [ ] Øk andel tidsriktige originalkilder på hele løpsdager og bevis uforanderlig `source_published_at`, original startliste og scratchrevisjoner; 0 PIT-attestasjoner i faktisk 169-løpsarkiv.
- [ ] P0 original resultatkode `place=0`/`kmTime=0,0` for Skive #8 må tolkes av offisiell kontrakt før selv et **papir**-tap kan bokføres.
- [ ] CORE-004 market-free kildefaktorgrunnlag og forhåndsregistrering, deretter **nye** kronologiske OOS-dager. Fremtidig ytelse/profit kan ikke konstrueres fra fortid.

