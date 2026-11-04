# MVP-017 | Research health – distinguish current valid from last-known valid

**Independent, read-only offline research status. No new original, PIT, betting signal, model refit, database or production write.**

## Acceptance contract

`mvp017_research_health` reads **only** explicitly identified, SHA-pinned original DEV-013 scorecard and DEV-011 manifest pairs. The caller supplies authenticated GitHub run metadata separately; the code checks each source JSON SHA-256, its internal manifest/scorecard inventory SHA agreement, physical `race_id` deduplication and consistency of model pairs/treble counts. The program **does not authenticate the caller-supplied GitHub run ID/HEAD itself** (`run_metadata_independently_authenticated=false`). `INCOMPLETE_ORIGINAL_COVERAGE` remains a valid *report* only if its source join is valid; it is not research P0 clearance.

State model:

| Health state | Semantic |
| --- | --- |
| `CURRENT_VALID` | Latest supplied run has original-consistent scorecard, not necessarily all race sources complete |
| `LAST_KNOWN_VALID` | Latest supplied run had a source error or conflict; use older, separately verified original **with old run ID/time**, not relabelled current |
| `SOURCE_UNAVAILABLE` | Latest source unreadable and no older verified source supplied |
| `INCONSISTENT` | Source claims (e.g. false 0/0/0 result during inventory outage) contradict original contract, and no earlier verified source supplied |
| `NOT_EVALUATED` | No source runs supplied |

Every output separately exposes `latest_supplied_run_status`, `latest_source_reason`, `last_verified_run_id`, `last_verified_counts`, source SHA and timestamp. Counts for an unresolved latest run are **null**, never 0. Provenance is **not** restored by copying old counts into latest run.

## Original-based verification

Authentic SHA-pinned GitHub Actions originals:

- [Run 41814068321](https://github.com/Maremoo2/Betting/actions/runs/41814068321), original DEV-013 scorecard SHA `62b0d78ca75847d2f2bfe895af240e45eada96a7719aefe4f880c1da02cbe178` and DEV-011 manifest SHA `ecb4477a0ec5fc9c954862943ab8b39876d7b13c6adf701bf4e777eaa9f9df33`: **63 physical races, 16 scored pairs, 14 WIN triples**.
- [Run 41817026855](https://github.com/Maremoo2/Betting/actions/runs/41817026855), original false-zero scorecard SHA `be7604e5b9604aa5439769e716038ad863854588fb6340b8333b4f77392e4481` and official unusable inventory manifest SHA `b14c61c979c656e49da382d574f3416293303e582b3b864b646df592282c4ac7`. **Must report INCONSISTENT latest and older verified 63, never 0**.
- [Run 41820503559](https://github.com/Maremoo2/Betting/actions/runs/41820503559), scorecard SHA `8a8012777ac49256e95aab9f3f5e2555a938cb8117826d6f47ddb5410f2343e5`, manifest SHA `657b6f177e540c53f293f0beadb1ea0811130c544bf1f8a3cc185bf1ca831e94`: **CURRENT_VALID 64 physical races, 16 scored original pairs, 14 triples, 0 certified PIT**. Cumulative original coverage remains INCOMPLETE.
- [Main V1 System Audit run 41820373324](https://github.com/Maremoo2/Betting/actions/runs/41820373324), exact `v1-system-audit.json` SHA `9ecf547e1792522b15865163bff765c2a87ce90d5220496a7f9f46be369861a6`: temporal PASS; runtime replay FAIL (five); settlement FAIL (Skive #82); provider WARN (14 fetch errors, 12 letrot and 2 Rikstoto).

The CI test compares all six originals and the V1 original with fixed SHA and checks both historical states; it uploads only a **derived** read-only health JSON, not raw historical SQLite or user-sensitive source bodies.

## Deployment scope

This PR creates a **manual/offline research CLI** and CI original replays only. It does not silently change the scheduled CORE-003 workflow or choose today's latest GitHub run without a supplied manifest. A later authorized research-only orchestration step may use the GitHub API to construct a provenance-complete candidate manifest and invoke the CLI. No plugin permission, production writes, PIT attestation, model update or betting policy change is introduced.

Health status does not override DEV-011 source-admission contract, V1 FAIL, missing original retention, or `bet_authority=false`.
