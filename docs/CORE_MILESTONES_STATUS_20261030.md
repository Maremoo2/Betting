# Betting – oppdatert milepæloversikt, 30. oktober 2026

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

## Ny teknisk delmilepæl – uavhengig arkiv-E2E

[Dokumentert E2E-kontrakt og kilder](P0_ARCHIVE_RESTORED_E2E_20261030.md). En skrivebeskyttet, markedsbasert kontroll av **531 MB** arkivert SQLite ble gjennomført på nyeste Watcher-state: **732** beslutningsrader, **321** sammenlignbare markedsfordelinger, **316** samsvar, **5** avvik, **5/5** rekonstruert fra original WIN-kilde og bekreftet senere oddsvedlegg. Dette er **ikke** full HBI kombinert replay eller samme nevner som senere systemauditens 305 vurderte/426 hoppede. Den danske uoppgjorte Shadow-kupongen står fortsatt åpen og P0 `FAIL`.

Forslag til reproducerbar forsknings-CLI + syntetiske regresjonstester er i egen review-PR. Delmilepælen `ARCHIVE_MARKET_FORENSICS_EVIDENCE` er fullført på dette spesifikke datagrunnlaget; `ARCHIVE_CLI_INTEGRATED` er **IN_REVIEW** inntil CI/review/merge, og `CANONICAL_P0_PASS` er fremdeles **BLOCKED**.
