# Betting – milepæler og integrasjonsstatus per 30. oktober 2026

**Omfang:** Dokumentert status basert på `Maremoo2/Betting` main `9c15934999d67b7c6b2467df30d39d7c491a10d7`, de opprinnelige CORE-001–004 PR-ene, isolert arkiv-/testpakke 30.10 og eksisterende V1-audit. Denne PR-en er **kun forsknings-/diagnostikkode** med foreslått milepælstatus. Ingen autorisasjon til merge, produksjon, modellpromotering eller betting.

## Statusnøkler
- **MERGET:** På main, men ikke automatisk ferdig/validert.
- **PR / REVIEW:** I den foreliggende integrasjonsgrenen; ingen main-adopsjon.
- **SHADOW:** Ekte isolert kilde-/research-jobb, ikke V3.3 BET-godkjenning.
- **BLOKKERT:** Mangler primærbevis/kontrakt eller har P0 FAIL.
- **VALIDERT:** Krever datert kildegrunnlag og korrekt prospektiv test; ingen slik sluttstatus er gitt her.

| Milepæl | Status på main før denne PR-en | Dette GitHub-integrasjonsforslaget | Neste målbare port |
|---|---|---|---|
| CORE-001 – ett helt løp | MERGET (#72), baseline | Strengere as-of/fullfelt-historikk- og markedsvurdering på arkiv | Autentisk PIT-startliste/identitet for hver aktiv hest |
| CORE-002 – hele dagen | MERGET (#72/#73), historisk 9/31 (28.10) | Heldags- og landvis kilde-audit; tydelig nevner og blokkeringer | Økt sammenlignbar prospektiv FULLY_ASSESSED-andel, uten retrospektiv lekkasje |
| CORE-003 – prefetch | MERGET (#75–#77), isolert SHADOW | Skrivebeskyttet `core_pit_roster_verification`, tie-/klokkekonflikt- og identitetsgates | Immutable rosterhistorikk, før-T−4 bevis, landvis auditerte hele løpsdager |
| CORE-004 – flerfaktor | MERGET (#78) forskningskandidat | Datakvalitets- og prospektiv opptaksgate; ingen nye vekter | Verifisert siste-fem/form, klasse, kusk, startmetode; tren kun på PIT-gyldig kronologi |
| P0-REPLAY-001 | Åpen FAIL (fem legacy mismatch); #67 stopper nye falske vedheftinger | Minimal **diagnostikkrettelse** for ikke-prisede off-field -0.02-rader + negative tester | Reell uavhengig adjudikasjon, ingen omskrivning av frosset proveniens; V1 FAIL står |
| P0-SETTLEMENT-001 | Åpen FAIL – DK 14.10 løp 6, valgt #8, vinner #5 | `settlement_source_review` er dokumenterende, skriver ikke kvittering | Maskinlesbare komplette offisielle sluttresultater + vinnerdividende før oppgjør |
| P1 – prospektiv kalibrering | Ikke validert | Forskningsgate og protokollutkast; historisk land-/dag-baseline | Registrer eksperiment før første løp, untouched OOS med marked alene og Champion |
| Operativ betting | Ikke kvalifisert | **Ingen endring** | Separat HQ/betting-authority gate etter P0 og PIT/OOS, aldri auto-BET |

## Reproduserbare arkivfunn (ikke promotering)

- Retrospektiv, deduplisert kohort: **108 travløp i fem land**, hvorav **15** tilfredsstilte en avgrenset råkildekontroll ved konservativ T−4 og **0** var fullt PIT-attestert. Fordeling: SE 59/15, NO 16/0, DK 9/0, FR 20/0, DE 4/0 (totalt/kildeklart). Manglende og overlappende blokkeringsårsaker må ikke summeres til distinkte løp.
- Eldre dagsbaseline for 28.10: 9/31 ferdig analysert med den opprinnelige CORE-002-forskningsmotoren; denne må ikke sammenlignes ujustert med ny 108-løpskohort.
- **Fem** historiske replay-tilfeller kunne rekonstrueres fra kildeodds ved frosset tidspunkt i isolert state; **tre** inneholdt ekstra ikke-prisede `-0.02`-rader som ga false negatives i gamle `legacy_provenance`. V1 runtime replay skal **ikke** retolkes som PASS.
- Historisk modellbenchmark: **297** retrospektive sammenlignbare løp, gjennomsnittlig `combined – market` log-loss **+0,0503** (lavere er bedre), median **−0,0165**. 226 SE, 45 DK, 25 NO, 1 FR. Ingen preregistrert OOS-konklusjon.
- Datapåstander er **ikke** bevis for kildepublisering eller faktisk løpsstart. Prospektiv-porten gir aldri automatisk trenings-/promoteringstillatelse.

## CI, review og leveransegrenser

**I lokal utdypingspakke:** `PYTHONPATH=src python -m pytest -q tests`: **105 passed** på isolert testpakke. Det er ikke hele repositoryets testsett. CI for denne PR-en skal vise ekte `ruff check .`, `pytest -q` og protected-strategy-check før en eventuell HQ merge-godkjenning. Arkivbasert E2E må kjøres separat på uendret SHA-256-verifisert state; ingen rå HBI SQLite eller private payloads committes.

**Ferdiggjøringsrekkefølge:** (1) CI og code review på integrasjonsgren; (2) append-only replay-adjudikasjon og offisielt dansk resultatbevis; (3) forbedre source-PIT ved T−4 i hele løpsdager og land; (4) preregistrere P1-protokoll, trene CORE-004 etter PIT-klar data; (5) evaluere uten etterpåklokskap og holde real-money OFF.

**Rollback:** Steng PR uten merge eller revert forsknings-/diagnostikkcommit; ingen historiske eller operasjonelle data er skrevet.
