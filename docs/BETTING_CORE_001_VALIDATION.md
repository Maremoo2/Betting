# CORE-001 – teknisk validering

## Kontrollert grunnlag

- Kodebasen `Maremoo2/Betting`, `src/hbi/fundamental.py` (Champion V1.1) og `src/hbi/shadow.py` gjennomgått 30. oktober 2026. Champion-formelen er reimplementert **for analyse**, ikke erstattet i produksjonskoden.
- Historisk SQLite: `hbi-state-2026-10-28.zip`, utdrag fra arkivert `data/hbi.sqlite`.
- Løp: `RIKSTOTO:S2_NR_2026-10-28:4`, Solvalla (SE, trot), 2026-10-28 18:27:00 UTC oppført start, as-of 18:23:05.413188 UTC.
- 12 oppførte hester, én strøket. Komplett fundamentalkohort kl. 18:23:05.383608 UTC, komplett vinnerodds-kohort kl. 18:23:00.000155 UTC.
- 11/11 aktive hester har kildeført total starter/seire; modellen setter historisk seiersrate med prior-starter 6 og normaliserer over aktivt felt.
- Arkivert lagret Champion V1.1 `fundamental_model_runs.probabilities_json` sammenlignet hest for hest: **identisk 11/11**, maksimalt absolutt avvik **0.0**.
- Sum p(win): **1.000000000**; 7 `WATCH`, 5 `PASS` (inkludert strøket), 0 `BET`.
- Formel: `fair=1/p`, `EV=p*odds-1`, `minimum_watch=fair*(1+0.05)*(1+0.05)` = 1.1025 × fair. Dette er en **ny, separat forskningsgrense** og IKKE et vedtak om å endre en frossen BET-grense.

## Reelle felter som ennå ikke støtter flerfaktormodell

- Historiske starter/seire: 11/11 aktive.
- Startposisjon, kusk og trener: 11/11 aktive som metadata; **ingen kalibrert effekt** inngår i p(win).
- Distanse på løpsnivå: **mangler i race-tabellen** for eksempelløpet.
- Fersk inneværende-år-form, auto-/voltrekord: **0/11** registrert i valgt fundamentalkohort.
- Baneforhold, tempo, klasse, aktuelle opptredener og kuskeffekter: ikke estimert.

## Alternativt løp som skal blokkeres

- Solvalla 28/10 løp 1 kl. 17:15 UTC med cutoff 17:11 UTC: ingen kanonisk løperliste eller marked/fundamentalt datasett i arkivet; `PASS – BLOCKED`.
- Solvalla 28/10 løp 6 kl. 19:16 UTC med cutoff 19:12 UTC: ingen komplette kilder; blokkert. Ved senere historisk cutoff (under 1 min før) foreligger 15/15 aktive løpshester. Dette er *ikke* en gyldig T−4-vurdering.

## Arkitekturskille: fundamental uavhengig av marked

`fundamental_ready_for_research` og `win_market_complete` beregnes hver for seg. Hvis alle hestene har kildebelagt historikk men vinnerodds mangler, produseres fortsatt fundamentale p(win) og fair odds for hele feltet. Handling blir PASS når pris-/markedsgrunnlaget er ufullstendig. Dette hindrer at markedssvikt maskerer fungerende prediksjonsdekning.

## Testresultat

- `python -m pytest -q tests`: **28 bestått** med kompakt ekte arkivuttrekk.
- Tester: eksakt Champion-formel, alle felt, sum-til-1, odds/EV, manglende felt/odds/historikk/kilde, strykninger, duplikater, framtidsstempler, for sent, bortfall av hele felt, historisk tidsavgrensning og rapporteksport.
- Testingen gjøres i en isolert pakke; full GitHub CI og produksjonspipeline er ikke kjørt.

## Prospektiv risiko

Observerte arkiv-tider sier ikke nødvendigvis når informasjon var tilgjengelig eller når start faktisk fant sted. Markedsodds er totalisatorpriser i bevegelse. Den enkle Champion-modellen er ukalibrert og kan produsere urimelig stor teoretisk EV. Følgelig er `WATCH` et teknisk screeningsignal, **aldri** et `BET`.
