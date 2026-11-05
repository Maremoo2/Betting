# MVP-021 P1 | Beslutningsgrunnlag for EU-lokalisert originalarkiv

**Dato:** 5. november 2026 · **Beslutningsstatus:** `OWNER_APPROVAL_REQUIRED / NO_DEPLOY`. Ingen beholdning er lastet til eksternt lager. Denne vurderingen endrer ikke infrastrukturen.

## Hvorfor nytt arkiv må besluttes

CORE-003 hadde autentiske `PAGINATED_GITHUB_INVENTORY_UNAVAILABLE` og `gh run download` HTTP 403 rate-limit til GitHub App (jf. #145). Tidsbestemt GitHub Actions-retensjon, 4 509 gjenfunne listeoppføringer og 46 sidekall per full vurdering gir en unødvendig sårbar kilde- og API-kjede. V1 audit [41985710357](https://github.com/Maremoo2/Betting/actions/runs/41985710357) beviser at én watcher-state nå kan reproduseres med SHA: original `hbi-state` 13372739243 er **206 013 908 ZIP-bytes**, mens restaurert SQLite er **707 309 568 bytes**. Denne STORE databasen må ikke ukritisk dupliseres hver femte minutt i et permanent WORM-lager.

**Kildehierarki:** (1) tidsriktige rå offisielle API-/PDF-kilder, (2) Collector-originaler med provenance, (3) uforanderlig modell og WIN/frozen as-of, (4) postrace offisielle complete+raceday, (5) SHA-pinnede derived index/scorecard. Feilede provider-forsøk og ufullstendige originaler lagres som separate metadata, aldri promoveres som bestått.

## Foreslått minstearkitektur

- **Region og WORM:** eiergodkjent Azure Storage Blob (Blob Storage GPv2) i valgt EU-region (for eksempel West Europe) med **version-level immutable storage, time-based locked retention 365 dager og legal-hold-støtte**, alternativt S3 i en valgt EU-region med Object Lock compliance mode. Region, dataoverføringsbetingelser, tjenesteavtaler og lisens/terms må godkjennes før installering.
- **Objektnøkler uten mutable overskriving:** `provider/<yyyy-mm-dd>/<physical-race-id>/<endpoint-kind>/<UTC-observation>/<SHA256>.raw` og `receipts/<SHA256>.json`. Raw SHA er over de **nøyaktige mottatte bytes**, ikke JSON serialisert på nytt. Avvis `source_sha_mismatch` og `cross_race_identity_conflict`; aldri endre gammel blob eller markere GET som «før T−4» basert på en senere kopi.
- **Manifest:** `provider, country, physical-race-id, source-URI, request_start_utc, fetch_completed_utc, source_published_at_utc=null unless explicitly provider-attested, HTTP status, response headers, raw-content-length, SHA256, Collector-run SHA, fullfield/identity/scratch state, original-to-derived parent SHA, schema version, TTL/retention, bet_authority=false`. Hash and append-only manifest. Representer `403`/null HTTP separat fra 200.
- **Privilegier:** separat kortvarig `raw-writer` (create only), `audit-reader` (GET/list), og `retention-admin` med to-personers eiergodkjenning. Managed identity/OIDC der mulig; ingen langlivede nøkler i GitHub Actions; encryption at rest/TLS in transit; privat nett/least privilege; logging av access; slettepolicy kan ikke overstyre WORM-låsen.
- **Retensjon:** foreslå 365 dagers uforanderlig rå kilde-retensjon som *startforslag* (eier/legal kan kreve annet), 30 dager hot-tilgang, senere «cool» for samme immutability-objekt hvis leverandør støtter det; en liten indekserbar SHA-manifesthistorikk bevares i fem år under egen godkjent policy. Database-snapshots er særskilt: daglig én SHA-pinnet, tilgangsstyrt kopi i 30 dager, ukentlig recovery i 90 dager; unngå 5-minutters WORM-kopi av hele SQLite.
- **API-budsjett:** GitHub artifacts beholdes som transient bygge-/QA-kanal, ikke permanent primærkilde. Cache manifest SHA og nedlastingsstatus. Delvis GitHub-side eller ett kilde-GET 403 => `BLOCKED_SOURCE`, sist godkjent benchmark beholdes. Sett eksplisitt maks GET og retry-after/backoff; ingen evig `gh run download`-loop.
- **Restore-tester:** hver dag uavhengig les-back på tilfeldige originale byte-objekter, rehash SHA. Hver uke isolert restore av scorecard+modell+offisielle resultater uten nettverkskall til provider; hver måned kontrollert full disaster recovery i en ny skrivebeskyttet arbeidsflate. Registrer tidsbruk, SHA og kilden som feilet. Ingen test får skrive til kanonisk HBI-state.
- **Observability/exit:** `source_write_success`, 24h `bytes_verified`, fail-closed `download_missing`, `WORM_policy_locked`, API-ratebudsjett, restore RPO/RTO måles; godkjenning krever at en ny løps-ID følger hele kilde-til-scorecard-kjeden uten at ekstern original kan omskrives.

**Teknisk metodebelegg:** Microsofts dokumentasjon om [Azure Immutable Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview) beskriver tidsbasert retensjon, legal hold og objektversjonering. [Azure Blob-priser](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/) må hentes for den valgte regionen/tilgangsklassen før budsjettvedtak. [AWS S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) skiller Governance og Compliance. Dette er **teknisk mulighet**, ikke lisens- eller juridisk godkjennelse.

## Beslutningsklar kapasitets-/kostnadsmodell

La `D` være gjennomsnittlig **NYE, dedupliserte, komprimerte** kilde-GB/døgn og `R` retensjonsdager. Stabil originalmengde `S≈D×R` GB. For illustrasjon med `R=365` og en **ikke-verifisert kalkulasjonspris** på €0,02/GB per måned (IKKE et Azure-tilbud):

| Scenario | Ny råkilde/døgn | Volum ved 365 dager | Illustrativ grunnlagring/mnd |
| --- | ---: | ---: | ---: |
| Lav | 0,5 GB | 182,5 GB | €3,65 |
| Middels | 10 GB | 3 650 GB | €73 |
| Høy | 100 GB | 36 500 GB | €730 |

**Ikke inkludert:** GET/PUT, metadata/manifest, cold rehydrate, minste lagringsperioder, backupkopier, regional redundans, WORM-versjoner, transfer/egress, logging, Key Vault, nettverk, moms eller dev-testmiljø. Tallene er kun følsomhetsberegning; faktisk pris krever **region- og datamengdespesifikt tilbud**, en prøvemåned uten deploy av permanent arkiv, eierbudsjett og signert retention policy.

## Påkrevd eierbeslutning

- [ ] Region, leverandør og EU-datalokasjon; juridisk vurdering og GDPR/leverandørvilkår.
- [ ] Varighet 365 dager vs annen vedtatt WORM-retensjon; særlige legal holds.
- [ ] Objektklassifisering og hvilke originaltyper som skal beholdes.
- [ ] Faktisk ingest GB/døgn og prisestimat etter måling; månedlig budsjett.
- [ ] Rollefordeling, IAM, logger og tilgangsrevisjon; recovery-eier og rutine.
- [ ] Separat eksplisitt deploy-godkjenning. Til da status `BLOCKED_INFRASTRUCTURE`.

**Absolutt:** Ingen endring av Champion/CORE-004/V3.3.12, PIT, BET/WATCH/PASS, staking, historiske beslutninger, settlement eller `bet_authority=false`.
