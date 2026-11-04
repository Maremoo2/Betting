# MVP-017 | Private original archive, local implementation and migration gate

**Status: CODE_COMPLETE locally only, permanent external retention BLOCKED_INFRASTRUCTURE.**
Repository baseline at design start: `2937150ee0ce5bb7a0f6bb2ebe9ede7b894d01d3`.
No live/archive/provider writes. This is not PIT attestation, evidence publication-time verification or production admission.

## Current source of truth and the retention problem

The ordinary CORE-003 GitHub Actions workflow publishes immutable-at-upload research artifacts, normally retaining individual sources/scorecards **21 days** and isolated research SQLite state **7 days**; PR-only original replay artifacts retain **30 days**. Cumulative DEV-011 inventories everything currently retrievable but cannot create prior bytes when GitHub retention expires. Original model reports lacking a valid `cohort-index.json` are not made admissible by possession of `shadow.json`. One original official-result receipt conflict remains.

## Implemented, local only

`python -m hbi.mvp017_private_original_archive` exposes `store` and `verify` to a caller-chosen local directory. It has no default destination, external network or GitHub integration. Ingestion requires explicit `approval_id`, source provider, endpoint **path with no query or credentials**, an explicit UTC observation-time claim, GitHub source run and artifact ID, optional physical `race_id` and independently known model SHA. Each source is copied byte-for-byte to `sha256/<prefix>/<digest>`; a canonical append-only provenance receipt is written to `receipts/<digest>.json`. Existing blobs are compared by SHA and never overwritten. Receipt writes use exclusive creation and no-follow. A repeated identical receipt is refused, while different provenance for identical bytes is preserved. The local root and subdirectories require private mode; any tampering fails the read-only `verify` check.

**Security boundary:** only explicitly reviewed non-sensitive originals may be ingested. A conservative detector rejects recognizable bearer or API-secret strings but is **not sufficient to certify all bytes non-sensitive**. Tokens/credentials are never copied from environment variables by the module and endpoint query strings are prohibited. The caller's `approval_id` is **not** a claim that a provider clock, publication time, model freeze, PIT or settlement has been independently verified. Receipts intentionally record these as claims and `independent_provider_clock_attested=false`; `bet_authority=false` is invariant.

Unit tests cover exact SHA, duplicate provenance, multiple receipts on a single original SHA, tampering, symlinks, unsafe permissions, secret/key patterns, invalid clocks and prohibition of a PIT/admission decision. PR CI uses existing genuine CORE-003 `cohort-index.json` original from GitHub run `41796128435`, SHA `ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0`. Original bytes remain **inside ephemeral CI scratch**, and only metadata-only replay evidence is uploaded. This proves local behavior, not permanent archival availability.

## Deployment architecture (not yet approved)

1. Security owner identifies a **private, tenant-controlled** object store with versioning, immutable/WORM retention and no public reads. Name, owner, region, minimum retention, lifecycle, legal/privacy basis and pricing are currently **not independently authorized**.
2. Grant narrow write-only identity to an isolated archive service and separate read-only audit identity. Use least privilege, encryption at rest, explicit secret rotation and immutable audit logs. Do not grant a research scoring job permission to delete or overwrite originals.
3. Before any source migration, inventory original GitHub artifacts through complete stable pagination and a SHA-verified artifact manifest; explicitly mark expired/missing/conflicting originals. Never backfill originals by reconstructing JSON from an output or inventing a source receipt. Export only pre-reviewed non-sensitive source bytes and metadata.
4. Append bytes and receipts under content-derived keys, read back independent SHA and size, record source GitHub run/artifact IDs, physical `race_id`, freeze SHA and observation clocks with explicit provenance confidence. Use version lock / compare-and-create semantics; conflicts remain BLOCKED.
5. Define a restore/read-only interface that verifies original bytes and receipts and refuses symlink, mismatched SHA, wrong original identity and after-cutoff observations. Only after **independent accepted integration tests** should cumulative scorecards be permitted to read from this archive.
6. Monitor ingestion audit, missing receipts, duplicate original SHA with different metadata, retention horizon and restore drills. There is no retroactive PIT authority or historical scoring promotion.

**Decision:** `BLOCKED_INFRASTRUCTURE` for long-lived remote original preservation. This PR adds only a testable, explicit local integrity primitive. Do not connect it to workflows or external storage without additional authorized configuration and review.
