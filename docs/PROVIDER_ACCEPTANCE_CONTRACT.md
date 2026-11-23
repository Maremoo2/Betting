# Provider-akseptanse – NO/SE trav

Gjeldende produktkontrakt fra 23. november 2026, etter eksplisitt HQ-instruks:
produktet omfatter norsk og svensk trav. Begge land er obligatoriske. Et fransk,
dansk eller galoppsfelt kan ikke erstatte et manglende norsk/svensk travfelt.

`HBI Provider Live Smoke / live-smoke` er produktkontrollen. Den bruker
`HBI_SMOKE_REQUIRED_COUNTRIES=NO,SE`, og må ha et komplett godkjent travfelt
fra hvert land under de eksisterende provider-, historikk- og modellportene.
Tom kalender, ufullstendig felt, manglende identitet/historikk og avvik mellom
providerkontroll og modellport er fortsatt feil. Ingen grense, identitetspolicy,
T−4-regel eller modellvekt endres. Provider-akseptanse er ikke full PIT-akseptanse.

Jobben `DK/FR diagnostics (non-blocking)` kjører samme kontroll med DK/FR som
separat omfang. Den har jobbens `continue-on-error: true`; derfor er grønn samlet
workflow ikke dokumentasjon på godkjente DK/FR-kilder. `diagnostic-status.json`
bevarer faktisk stegutfall, og `diagnostic-smoke.json` bevarer feilkoder og
feltresultater i et separat artefakt. Den bredere provider-research-proben ligger
også her, slik at markeder utenfor produktet ikke blokkerer NO/SE-akseptansen.

Kun de to eksakte omfangene NO/SE og diagnostisk DK/FR tillates. En feilkonfigurert
enkeltlandskontroll eller tom konfigurasjon kan ikke gi redusert produktakseptanse.
Begge kjøringer oppgir omfang, påkrevde land og antall aktuelle travløp per land.

GitHub-regler, godkjenningsetiketter og strategi-/providerregister er uendret.
Denne endringen er ingen bettingautorisasjon eller produksjonsaktivering.
