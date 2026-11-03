# Betting MVP – én-prosjekteier og merge-styring

**Gjeldende fra 3. november 2026 (MVP-005).** Dette dokumentet erstatter tidligere administrative krav om uavhengig menneskelig HQ-review. Prosjekteieren (Maremoo2) har uttrykkelig besluttet å styre godkjenning selv. Dette er en *administrativ endring*, ikke en endring av kildekontroller, PIT/BET-krav eller modellmetodikk.

## Merge-kontrakt: teknisk kontroll + eksplisitt eiersamtykke

1. Identifiser **eksakt siste PR-HEAD-SHA**, og kontroller hva som er endret siden forrige tekniske evaluering. Ved nye commits må relevante tekniske kontroller testes på den nye HEAD-en.
2. Krev beståtte, relevante automatiske tekniske kontroller: `test` (Ruff, pytest og den autentiserte historiske Collector → SQLite → forskningsmodellregresjonen), `v1-integrity` og `protected-strategy`. Bevar originale SHA-256, source lineage og negative integritetstester. Dokumenter andre feilede kontroller og vurder faktisk teknisk relevans; ikke marker feil som PASS.
3. Forskningsstatus `research_model_eligible` er **ikke** `model_input_approved`, `INDEPENDENT_PIT_CERTIFIED` eller `BET_ELIGIBLE`. Ingen kode-merge gir PIT-sertifisering, modellkalibrering, real-money-autoritet, autospill eller endringer i V3.3.12/BET-hardgates.
4. **Kun prosjekteieren** gir uttrykkelig tillatelse til merge når den dokumenterte tekniske kontrollen er fullført. En oppdragsbeskrivelse eller tillatelse til å oppdatere en PR er **ikke** merge-autorisasjon. DEV og Roadmap stopper ved oppdatert PR uten særskilt mergegodkjenning.

## Ikke lenger obligatorisk

- Ekstern eller uavhengig menneskelig reviewer, ekstra GitHub-konto og godkjennende PR-review.
- Repository-variable `HQ_REVIEWER_LOGINS`, eksakt `APPROVED_FOR_MERGE`-kommentar og tidligere `independent-hq-review-evidence`-workflow.
- GitHub branch protection eller ruleset som mergeforutsetning. Slike innstillinger er valgfrie og skal ikke forsinke MVP. De kan ikke slå av tekniske kilde-/PIT-/BET-sperrer i programmet.

Den gamle, ikke-aktive evaluatoren `scripts/hq_exact_head_review_gate.py` og tilhørende offline-tester beholdes **kun som historisk kode** ved denne minimale PR-endringen. De er ikke en aktiv statuskontroll eller obligatorisk prosess; ingen skal konstruere eller kreve en uavhengig godkjenning.

## Teknisk kontroll og tilstand

- `test`, `v1-integrity`, `protected-strategy` forblir de sentrale automatiserte kode-/integritetskontrollene. `live-smoke` for SE, DK, NO og FR beholdes synlig som egen datadekningsdiagnostikk. Dansk `NO_FULL_FIELD_LIVE_PASS:DK` er ikke dokumentert som regresjon i Collector-integrasjonen. Ingen dansk dekning skal påstås før det finnes et faktisk bestått dansk fullfeltsbevis; dersom landdekning er et eksplisitt akseptkrav for en endring, må den kontrolleres separat.
- Allprospektiv PIT T−4-attestasjon krever reelle originaler, dokumenterte klokker, matchende revisionskjede og uavhengig attestasjon. Historiske `HISTORICAL_REPLAY`-resultater kan ikke brukes som prospektivt PIT-bevis.
- Hvis teknisk CI feiler på HEAD, er PR teknisk blokkert. Hvis eneste røde check er en klart separat datadekningsdiagnostikk, skal den forbli RED i rapporteringen, men klassifiseres etter sitt faktiske omfang i stedet for å behandles som automatisk Collector-kodefeil.
- Ingen manuell `workflow_dispatch`, merge, aktiv produksjonsendring eller endring av bettingterskler/innsats uten egen, uttrykkelig beslutning fra prosjekteieren.

## PR #121 og MVP-frister (per 3. november 2026)

- PR: https://github.com/Maremoo2/Betting/pull/121
- Verifisert funksjonell start-HEAD før denne administrative oppdateringen: `0a629a8d794af5c1a1d68e68ede14aa68990e59e`.
- 4. november: dokumenter ny HEAD, tekniske tester og konkret mergeplan.
- 6. november: betinget merge **bare etter eksplisitt eiersamtykke** og godkjente tekniske krav.
- 10. november: forsøk et reelt prospektivt norsk/svensk T−4-løp *etter* eventuell merge, uten å konstruere data eller etterdatere klokker.
- 13. november kl. 18:00 Europe/Oslo: teknisk MVP-aksept eller eksakt dokumentert `BLOCKED`/`NOT_OBSERVED`; ingen automatisk BET-autorisasjon.

Se `docs/ROADMAP_MASTER_EXECUTION_20261030.md` for oppdatert kritisk sti. Eldre omtale av uavhengige reviews i arkivhistorikken nedenfor er historisk og **ikke gjeldende prosedyre**.
