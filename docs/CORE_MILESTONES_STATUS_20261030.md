# Betting – oppdatert milepæloversikt, 30. oktober 2026

> **NY HOVEDOVERSIKT 30.10.2026:** [ROADMAP_MASTER_EXECUTION_20261030.md](ROADMAP_MASTER_EXECUTION_20261030.md) viser oppdatert kode-/kildefremdrift, konkrete akseptanser, P0 offisielt oppgjørsbevis, CORE-003 falsk T−4-positiv og åpne GitHub-spor. Eldre tekst nedenfor beholdes som historisk progresjonsgrunnlag; dagens status står i hovedoversikten.


> **Kildehierarki:** GitHub `main` ved merge `e328c196ea236053536a9134e0b8dc89e26f0924` ([PR #80](https://github.com/Maremoo2/Betting/pull/80)), faktisk HBI V1 systemaudit [41107698547](https://github.com/Maremoo2/Betting/actions/runs/41107698547), Watcher-state [41105795195](https://github.com/Maremoo2/Betting/actions/runs/41105795195) og isolert CORE-003 Shadow-pilot [41106155052](https://github.com/Maremoo2/Betting/actions/runs/41106155052). Status er oppgitt per kohort og dato, aldri som en udokumentert generell forbedring.

**Definisjon:** `MERGET` = kode finnes på main. `SHADOW` = faktisk isolert kilde-/forskningskjøring. `REVIEW` = foreslått ny kode/diagnostikk, ikke merget. `BLOCKED` = uoppfylt hardport. `VALIDATED` = krever independently attesterte PIT-data og urørt prospektiv testing; ingen slik status her.

| Milepæl | Dokumentert utført | Status 30.10 | Neste akseptansekriterium |
| --- | --- | --- | --- |
| **CORE-001 ett løp** | Fullfelt-baseline med separat markedsmodell i [#72](https://github.com/Maremoo2/Betting/pull/72), strengere kilde-/PIT-gates merget i #80 | **MERGET, RESEARCH** | Ett *uavhengig PIT-attestert* fysisk løp med full aktiv identitet, tidsriktig historie og WIN-marked |
| **CORE-002 hel løpsdag** | Dagsmotor og full blokkeringstrakt i #72/#73, ekstra kildeaudit i #80 | **MERGET, RESEARCH** | Samme denominator/kohort under prospektiv full-dag T−4; øk faktisk dekning fra historiske 9/31 (28.10) |
| **CORE-003 kildeinnhenting** | #75–#77 + isolert Shadow-pilot; PIT/roster-kontroll i #80 | **SHADOW-OPERATIV, IKKE PIT-VALIDERT** | Versjonert kildepublisering, immutable starter-/scratchrevisjoner, faktisk fullfelt-T−4 per land og dato, [#83](https://github.com/Maremoo2/Betting/issues/83) |
| **CORE-004 flerfaktormodell** | Beskyttet, *ufittet* forskningskandidat #78 og forskningsopptaksport #80 | **MERGET, IKKE TRENT/VALIDERT** | PIT-verifisert nyere form/kusk/klasse/distanse og pre-registrerte vekter, deretter kronologisk out-of-sample |
| **P0-REPLAY-001** | Rotårsak fra 5 historiske vedheftinger dokumentert 27.10; #80 forbedret `-0.02`-håndtering i read-only diagnose | **HBI V1 FAIL – ÅPEN [#81](https://github.com/Maremoo2/Betting/issues/81)** | Stabilt hash-/tidsstempelbevis i separat PR; *uavhengig adjudikasjon* og eksplisitt HQ-klarering, uten omskrivning eller waiver |
| **P0-SETTLEMENT-001** | Skive 14.10 papirvalg #8/vinner #5 isolert; #80 har kun kilde-review | **HBI V1 FAIL – ÅPEN [#82](https://github.com/Maremoo2/Betting/issues/82)** | Originalt `isComplete=true`, bekreftet deltakelse/plassering, vinnerdividende, deretter attestert isolert replay; ingen antatt oppgjør |
| **P1 kalibrering** | Retrospektiv markedsbenchmark, research-only opptaksport og *utkast* til prospektiv protokoll i #80 | **IKKE VALIDERT** | Preregistrert, låst før framtidige løp, urørt kronologisk OOS, kalibrering/edge/CLV målt separat |
| **Operativ betting** | Ingen real-money execution eller auto-promotion autorisert | **IKKE KVALIFISERT** | Alle P0/P1-porter + separat, eksplisitt HQ/betting-godkjenning |

## Faktisk progresjon og målt evidens

- **PR #80 er merget til main**; GitHub PR-CI var `1130 passed, 47 skipped`. `skipped` er ikke `passed`.
- **Etter merge:** faktisk gjenopprettet [HBI V1 System Audit 41107698547](https://github.com/Maremoo2/Betting/actions/runs/41107698547) ble **FAIL**: temporal PASS; provider WARN (11 fetchfeil); replay **304 sjekket / 425 skipped / 5 mismatches**; settlement **737 sjekket / 1 uoppgjort**.
- **Uavhengig originalkilderekonstruksjon:** latest state-artifact **13001685408**, SQLite SHA-256 `4f671ade4510247544c3b6a95e66f6a5c24681814fb4790adf98b847bf1b660e`: alle fem opprinnelige markedsodds matchende frossen p, alle fem vedheftede odds fra senere markeds-kohort. Det er ikke et PASS i V1; se [P0-kilderapport](P0_REPLAY_SOURCE_EVIDENCE_20261030.md).
- **Separat arkivdekning 27.–30. oktober:** 108 distinkte travløp, 15 konservativt råkildeklare (15 SE), **0 fullt PIT-attesterte**. Ikke sammenlign direkte med CORE-002 9/31 fra 28. oktober.
- **Senere isolert CORE-003-pilot:** 10 framtidige race-refs i fast kohort, ett svensk løp med 12/12 verifisert historikk og komplett WIN-kilde; et fransk 17-hesters løp blokkeres av `LETROT_FULL_FIELD_CORROBORATION_FAILED`. `roster_pit_verified=false`, ingen BET.
- **Tidligere retrospektiv P1-deskriptiv analyse:** 297 løp, markedsbaseline bedre enn kombinert modell i gjennomsnitt (delta combined-minus-market log-loss +0,0503), ikke en urørt framtidig modelltest.

## Prioritert arbeid / stopplinje

1. **P0-REPLAY-001:** dokumenter eksakte, kildehash-bundne mismatch og får kontrollert append-only adjudikasjon. Ikke senk toleranse, skjul gamle misforhold eller merk V1 PASS uten bevis.
2. **P0-SETTLEMENT-001:** hent offisielt resultat og dividende i autorisert kilde-/testmiljø. Ikke bokfør -25 NOK uten primærbevis og separat godkjennelse.
3. **CORE-003:** forbedre *faktisk* immutable PIT-kildekobling og fullfeltforsøk på flere racingdager/land; bevar denominator.
4. **CORE-004/P1:** bare etter PIT-klar data – forhåndslåst hypotesetest og uavhengig markedsbaseline; ingen modellpromotering ved grønn kode-CI alene.
5. **Operativ betting:** OFF. Ingen autospill, tidsplan-/stakingendring eller Sheet-write.

**Ny forsknings-PR om replay-evidens er kun en REVIEW-leveranse.** Ingen strategi-, frozen history-, audit-waiver- eller produksjonsrettigheter følger av denne roadmapen.

## Operativ status fra faktiske GitHub-runs 30. oktober 2026

**Hovedgren:** [PR #80](https://github.com/Maremoo2/Betting/pull/80), [PR #84](https://github.com/Maremoo2/Betting/pull/84) og [PR #85](https://github.com/Maremoo2/Betting/pull/85) er **MERGET**; main ved `fc59aae82d41c03c32faca155c22261232a0d8fd`. [PR #86](https://github.com/Maremoo2/Betting/pull/86) er **åpen** som en isolert E2E workflow-/dokumentasjonsendring, ikke en godkjent merge.

**Nytt, etterprøvbart P0-delresultat:** [Github Actions P0 pinned archive 41116541999](https://github.com/Maremoo2/Betting/actions/runs/41116541999) **PASS på nøyaktig arkivkontroll**. Original SQLite SHA-256 `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0`, 732 beslutninger, 321 sammenlignbare WIN-markedsreplay, 316 match, **5 mismatch**, **5/5** samme original-/senere odds-kilde og **én uoppgjort Shadow-kupong**. Reproduserbar rapport i Github artifact `p0-archive-e2e-41116541999` (ID `13005058521`), SHA-256 `ad93d78b229fa8eb96687f28571fe636903b034893eaa9e6e55cc81c5a46445f`. Databasen uendret.

| ID | Leveranse | Kode-status | Faktisk evidensstatus | Målt neste ferdigport |
| --- | --- | --- | --- | --- |
| **CORE-001** | Et helt løp | MERGET / forskningsmotor | Foreløpig ingen PIT-attestert fullfeltstart | Ett komplett uavhengig kilde-/starttid-/felt-attestert løp |
| **CORE-002** | Helt dagskort | MERGET / forskningsmotor | Historisk 28.10: 9/31 på tidligere definisjon | Prospektiv hel-dag-kohort med full denominator og målbar økning |
| **CORE-003** | Pre-fetch og PIT | MERGET / operativ SHADOW | Retrospektiv 15/108 kildeklare, **0 PIT-attesterte**; piloter 0/10 og 0/12 komplett | Løs dokumentert kilde-ID/tidsavvik, historisk versjonert startliste, T−4 per land |
| **CORE-004** | Flerfaktorkandidat | MERGET / **ufittet** | Historikk/marked alene er ikke godkjent treningsgrunnlag | Verifiser nyere formdata og PIT-godkjent OOS, deretter forhåndslåst trening |
| **P0-REPLAY-ENG** | Skrivebeskyttet bevis- og arkiv-E2E | PR #84/#85 MERGET; PR #86 workflow i REVIEW | **Hash-låst faktisk CLI-run PASS, 5/5** | PR #86 code review/merge og arkivmanifest vedlagt #81 |
| **P0-REPLAY-INTEGRITY** | Historiske V1 parity | Åpent #81 | **FAIL**: fem mismatch i offisiell audit, selv om årsak rekonstruert | Uavhengig append-only adjudikasjon med explicit HQ-godkjennelse |
| **P0-SETTLEMENT** | DK 14.10 Shadow | Åpent #82 | **FAIL**: én kupong, 0 offisielle komplett-resultater arkivert | Offisiell `isComplete`, #8 deltakerstatus, vinnerdividende, isolert settlement-replay |
| **P1** | Prospektiv kalibrering | Gate/protokollutkast MERGET | **NOT_VALIDATED**; retrospektiv 297-løps markedsoverlegenhet ingen OOS | Låst urørt framtidig par-sammenligning av marked/Champion/kandidat |
| **BETTING** | Autoriserte spill | Uendret | **OFF / IKKE KVALIFISERT** | P0 + P1 + separat, eksplisitt spilleautorisasjon |

Merk at den reelle V1 combined-engine [audit 41111521341](https://github.com/Maremoo2/Betting/actions/runs/41111521341) undersøkte **305**, hoppet over **426**, hadde **5** mismatch og `settlement_integrity=FAIL`. Den kom fra **et annet db-tidspunkt** (731 beslutninger) enn den hash-låste WIN-only-kontrollen (732 beslutninger). De fem avviks-ID-ene matcher, men **nevnerne skal ikke blandes**. Kode-CI eller rekonstruksjon er aldri autoritet til å sette V1 PASS.

### Prioritert rekkefølge

1. **P0-REPLAY-ENG:** review/merge PR #86 etter all grønn CI og nøyaktig 732-row arkivrapport; dette lukker *teknisk reproduksjon*, ikke historisk V1.
2. **P0-SETTLEMENT:** innhent offisiell Rikstoto-resultatpayload/dividende for Skive 14.10 #8 på autorisert kilde, replay på isolert kopi; ingen håndskrevet -25 NOK.
3. **P0-REPLAY-INTEGRITY:** kildedokumentert formell append-only adjudikasjon; ikke skriv over gamle snapshots/decision_provenance eller reduser testnevner.
4. **CORE-003:** avklar `PROVIDER_RACE_IDENTITY_OR_TIME` på Romme #6 (12/12 hester matchet men hele kilden blokkert); ikke endre beskyttet gate uten godkjenning. Kjør reell T−4-dekningsmåling over hele dager, separat per land.
5. **CORE-004/P1:** forbedre verifiserte faktorer, preregistrer hypotese før nye starter, evaluer markedsbaseline og kalibrering OOS. Fortsett `PASS`/ingen real-money til særskilt godkjenning.

---

## Ny teknisk delmilepæl – uavhengig arkiv-E2E

[Dokumentert E2E-kontrakt og kilder](P0_ARCHIVE_RESTORED_E2E_20261030.md). En skrivebeskyttet, markedsbasert kontroll av **531 MB** arkivert SQLite ble gjennomført på nyeste Watcher-state: **732** beslutningsrader, **321** sammenlignbare markedsfordelinger, **316** samsvar, **5** avvik, **5/5** rekonstruert fra original WIN-kilde og bekreftet senere oddsvedlegg. Dette er **ikke** full HBI kombinert replay eller samme nevner som senere systemauditens 305 vurderte/426 hoppede. Den danske uoppgjorte Shadow-kupongen står fortsatt åpen og P0 `FAIL`.

CLI er **MERGET via PR #85**. En påfølgende hash-låst ekte GitHub Actions-run i **PR #86 har PASS**, men workflowen er ikke ferdig reviewet/merget. `ARCHIVE_MARKET_FORENSICS_EVIDENCE` og `ARCHIVE_CLI_INTEGRATED` er **DONE** på kodenivå; `PINNED_ARCHIVE_CI_EVIDENCE` er **VERIFIED** for kildesnapshotet; `CANONICAL_P0_PASS` er fortsatt **BLOCKED**.
