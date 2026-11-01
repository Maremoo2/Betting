# DATA-004: to uavhengige PDF-gjennomganger (forskningsprotokoll)

Dette er en **manuell kildeoppgave**, ikke en parseroppgave. Den låste holdouten består av 30 historiske rader × 13 felt = **390 felter** og 24 originale program-PDF-er. Ingen av feltene er automatisk fasitmerket.

## 1. Verifiser byte-identiske kilder

Hent de **sju opprinnelige GitHub Actions-arkivene** identifisert i `research/data004-holdout-source-pdf-evidence-v1.json`. Pakk dem ut i én separat, lokal forskningsmappe, slik at alle opprinnelige relative stier `output/daily/.../meetings/.../full_program.pdf` beholdes. Ikke lag nye PDF-er, slå sammen sider eller erstatt kildene med nyere nettsider.

Før den første transkripsjonen, kjør:

```bash
python -m hbi.data004_original_pdf_audit \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --source-root /path/to/original-archives \
  --blank-ledger-output /path/to/reviewer-A.csv
```

Kjør kommandoen på nytt med en annen utfil, `reviewer-B.csv`. Den avviser eksisterende utfil og leser alle original-PDF-ene om igjen. Kildesjekken kontrollerer SHA-256 og sidetall; **den leser eller merker ikke de historiske hesteradene semantisk**.

## 2. To reelle og adskilte gjennomganger

Gi hver person tilgang til de originale PDF-ene, den låste holdout-ID-listen og sin **egen** blanke CSV. Reviewer B får ikke se reviewer A sin fil eller parserens foreslåtte felt. Reviewer-ID alene verifiserer ikke at personene er uavhengige.

Behold eksakt kolonneoppsett, sample-ID, felt, opprinnelig parserstratum, møtenøkkel og PDF-hash. For hvert felt registreres faktisk PDF-side (`source_pdf_page`, 1-indeksert), etterprøvbar sideposisjon eller historisk rad (`visual_row_locator`), en navngitt `independent_reviewer` og én av følgende statuser:

- `GOLD_VALUE_RECORDED`: tydelig synlig og direkte avlest verdi; fyll `gold_value` med ordrett transkripsjon.
- `GOLD_UNAVAILABLE`: feltet kan ikke leses fra korrekt kilde/rad; la `gold_value` være tom og dokumenter undersøkelsen i `visual_row_locator`.
- `GOLD_AMBIGUOUS`: kilde/rad/kolonne er tvetydig; ingen oppdiktet eller antatt verdi.
- `PENDING_VISUAL_REVIEW`: ikke gjennomgått. De fire kildehenvisnings-/reviewkolonnene og `gold_value` skal fortsatt være tomme.

Særlig er manglende galopp- eller diskvalifikasjonsmarkering **ikke** automatisk `False`. Ikke trekk fasit fra modellscore, tidligere parserresultater, løpsutfall, nyere kilder eller automatiske antakelser.

## 3. Sammenlign to ferdige transkripsjoner

```bash
python -m hbi.data004_dual_review_audit \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --source-root /path/to/original-archives \
  --review-one /path/to/reviewer-A.csv \
  --review-two /path/to/reviewer-B.csv
```

Kommandolinjeverktøyet gir et JSON-sammendrag, kontrollert input-SHA-256, antall felter begge har gjennomgått, antall uenigheter og en konkret uenighetsliste. **Exit 2** ved uferdige eller uenige review-filer er forventet og må ikke tolkes som at fasiten er validert.

Selv om alle 390 transkripsjonene stemmer, er sluttstatus **`STRUCTURAL_CONSENSUS_REQUIRES_HUMAN_SOURCE_SIGNOFF`**, ikke godkjent fasit. En annen autorisert HQ-kontroll må visuelt attestere originalrad, sidetilknytning, vurderingsprinsipper og reell uavhengighet. Den menneskelige aksepten må dokumenteres separat og må ikke lages ved å endre `holdout_validated` fra `false` til `true`.

Ingen av disse kommandoene gjør produksjonsendringer eller autoriserer PIT, modelltrening, Champion, V3.3.12 eller BET.
