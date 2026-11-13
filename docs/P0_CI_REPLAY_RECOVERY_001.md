# P0 CI replay recovery

**CI_BLOCKED_SOURCE.** No byte-identical copy of the required historical SQLite was located in the examined sources. A restore remains possible if an authentic owner backup with the pinned SHA-256 surfaces.

## Historical baseline

The existing CI workflow requires `core003-pilot.sqlite` from `core003-pilot-state` in run `41518035718`, commit `81aa6e225f92616009dbc932f9a4e9364d804c62`, started 2026-11-02 20:18:37 UTC. The pinned SQLite SHA-256 is `60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0`. Artifact ID `13176561174` returns HTTP 404 even through the authenticated connector. Earlier #193 evidence documents the original upload and seven-day retention. No original ZIP digest was independently recovered.

Both surviving ZIPs were downloaded and independently hashed. The report ZIP contains only `core003-pilot-report.json`. The model ZIP contains the index and two sets of runner/model reports. Neither has a SQLite member.

| Artifact | Observed ZIP SHA-256 |
|---|---|
| Report 13176366330 | `ed9ceda89e70e17e0fc14628c99a85ee32fdae8e3c3a0e88d74ff5a1b456f8e0` |
| Model 13176001964 | `5e2f67323d51a3aa2701bd04a3abe5fe2b0699f4009f00cdecd3d1c26244b9e3` |

The local search hashed 21 databases and eight SQLite/DB members in 579 ZIPs under workspace outputs/raw and isolated Betting temp directories. No match. The checked newer hbi-state artifact `14019749009` held `data/hbi.sqlite` with SHA-256 `2d7c53155b7cf831aa9127614fb99d00f885b5e560207237c6f6b9f6b9f54ee8`. Other remote states were inventoried by artifact name and metadata. Their inner databases were not all downloaded. The active Windows state was outside the search scope.

[Historical run](https://github.com/Maremoo2/Betting/actions/runs/41518035718) · [Upload and retention evidence](https://github.com/Maremoo2/Betting/pull/193)

## Separate authentic baseline

The existing 12 November research replay produced artifact `13957950661`. Downloaded ZIP SHA-256 `030812fa1fcba89a5f61b2aa9365827f0c8c1d42ae4be52e5219cb0d390c5d24`. Independent SQLite SHA-256 `25772991b60cba13c05707b5862b65329af9db2a6a7a3ffd0c4311e3835f30ad`. SQLite integrity returned `ok`. The report pins Collector source ZIP `23871090f75ded32829fbc239ca6f1bae8be7d5784cc0f67c650a9aaeef639f3` and manifest `8c77f390cdc2a1e9a1fd214a49eab73ecc66fbf910ceb040919a53d01d1c5dac`. Actions verified PDF/startlist reconciliation, idempotent import and independent restore.

On fresh isolated copies of this authentic replay state, both exact PR heads evaluated 30 races / 321 starters. Each rejected 30 retrospective cohorts, calculated zero p(win), persisted zero predictions and had zero tickets. Other overlapping blockers were missing full-field cohort/evidence, unresolved permanent identity and unattested independent scratches. This baseline represents 12 November. The historical control remains mandatory.

[Separate authentic replay](https://github.com/Maremoo2/Betting/actions/runs/43247038338)

## Exact heads and CI

| PR | Head | State | CI |
|---|---|---|---|
| #195 | `52b23ff22c6af3f3cbe326734ac9d7d05e9458b5` | Already merged as `b41dfcd6d7c2b4aa1d6b61e641e47a0d7e1166c6` | Ruff/Pytest, protection, integrity, smoke and research/restore passed. Historical replay failed. CI_BLOCKED_SOURCE. |
| #196 | `bbd87c4cfdfda790474ee1e856c4f2a0bf02c2ec` | Draft, based on #195 branch | Same technical checks passed. Historical replay failed. CI_BLOCKED_SOURCE. |

Prior exact-head Windows runs had 2,116 passed, 125 skipped and the same 29 baseline failures. The 57 focused checks on each head covered identity receipts, full field, scratches, T−4 and no predictions on rejection. This recovery PR adds documentation and an independent authentic data check. It changes no test coverage or expectations. The reviewed diffs leave Champion, CORE-004, V3.3.12, production and the Windows watcher untouched.

[CI #195](https://github.com/Maremoo2/Betting/actions/runs/43388909079) · [CI #196](https://github.com/Maremoo2/Betting/actions/runs/43388966211)

If an owner backup surfaces, verify the original archive's provenance and exact SQLite hash before restoring the existing replay reference. Otherwise, the next concrete task is HQ review of the already verified 12 November replay as a separately retained baseline, with the historical source debt explicit. A decision about the mandatory historical gate requires separate HQ authorization.
