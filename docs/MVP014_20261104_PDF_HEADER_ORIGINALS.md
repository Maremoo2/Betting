# MVP-014 | 4 Nov 2026 PDF header/horse-weight false ambiguity – original proof

**P0 isolated Collector source parser fix.** The source of truth is genuine Collector GitHub run [41784797103](https://github.com/Maremoo2/rikstoto-program-collector/actions/runs/41784797103), artifact **13300048964**, archived 4 Nov 2026 at 06:20–06:21 UTC. This is a morning source replay and **NOT** T−4/PIT/production certification. Main baseline: `254ae4b5ec6c5e97622a1881b581e9c7d9c86f9b`.

## Original-based reproduction BEFORE change

Against the five physical-meeting original expanded PDFs and same-observation `/starts.raw.json`, the current HBI `collector_handoff.pdf_field()` parser matches **32/35** physical races and incorrectly rejects three with `COLLECTOR_PDF_PHYSICAL_RACE_AMBIGUOUS`.

| Race ID | Original field | Original PDF clock Oslo | Header content before `START KL` | Invalid extra number in first 14 extracted lines AFTER `START KL` |
| --- | ---: | --- | --- | --- |
| `RIKSTOTO:F1_NR_2026-11-04:4` | 16 runners | 15:05 | standalone `4` | `0` from first runner's form |
| `RIKSTOTO:S1_NR_2026-11-04:2` | 7 runners | 12:45 | `Løp 2` | standalone `62` horse weight |
| `RIKSTOTO:S1_NR_2026-11-04:5` | 9 runners | 14:00 | standalone `5` | standalone `59` horse weight |

Prior code extracted all *first 14 page lines* as header candidates. Depending on layout, the first horse's statistical weight or numeric form was already within these 14. Thus the code sees e.g. `{2,62}`, never `{2}`, even though it had already encountered the unambiguous START KL clock. This is a deterministic false rejection, not provider mismatch.

Original input SHA-256 receipts (checked against immutable original archive bytes):

| Meeting | `full_program.pdf` SHA-256 | `starts.raw.json` SHA-256 | Original physical races |
| --- | --- | --- | ---: |
| F1 | `b5b7f5999fed5241cef3c16b27cf31161c010822474b5417d97710e15f828496` | `3ad6930eaf0f6add093e6fb201076ba6c5a5c948eb49af087db6ca9b897bbd3b` | 8 |
| F2 | `28e2091b68d551ffc65aac7c03ccefc1a973c2066bcad5436a0d01a5cb740510` | `30f4db225d2fe04d169cb1e715f5dd4c388bdeeaf4b79ecfab869c00d3dfca04` | 4 |
| S1 | `f562baa4102b0c6655ffe1829e65369d8b48dc75de87fada3d03a5ab0b0b0210` | `1e4a6abf7b3212c896b4c8c6129d9f546804c93baf3fa53e7088cf25d7765d50` | 5 |
| S2 | `897c6c636d7c70c2ed106b3d8365061378e0e3d85dc41453c7ee2b2fbe463a01` | `b3da4823aafaaf2386dc89be37421fae1ca2242517298aff71d54b8f9a6fb420` | 10 |
| S3 | `ddbe3bf9fe96dd04492509c184de9ae6491e9660f4f2772d2b8f07645eb74ba2` | `fe1cde9c8642d8f526eb95c69c524c7b24243ba6669540f9126197e5ff4ea386` | 8 |

## Minimal fix and genuine regression AFTER change

In `pdf_field()`, restrict the existing *first 14 lines* for physical race label detection to **lines before the original first `START KL` line**. Keep original race-header pattern, unique physical race requirement, continuation-page limit, complete matching of every original runner number+name, unique source clock, DST-clock rejection, and all independent identity/PIT admission rules unchanged.

Isolated offline replay **after this one parser fix**: **35/35** source full-field PDF matches, including all three previously false rejected and Jägersro race 5's original nine-runner field. The tests also check a deliberately wrong runner name and unknown physical race number fail closed. The CI test fetches the genuine Collector original directly by run and artifact name, checks every fixed SHA-256 above and saves machine-readable per-meeting replay totals. No date or cutoff is moved backwards.

**Important admission restriction:** source PDF matching is only one check. Jägersro race 5's nine runner registration numbers are still `TMP` from the morning Collector /starts original; no stable Sportinfo/ATG/Rikstoto chain has been verified. This patch grants **no** `MODEL_READY`, PIT or BET authority by itself. The original result and full field remain unmodified.

## Project priority

Separate from DEV-013 PR #128 (already merged), DEV-011 source-quality classification PR #130 (draft), and the Jägersro 4 Nov 22:15 existing aftercheck. No historical backfill, no provider market substitution, no betting policy, no multi-leg economics, no merge without owner approval. Next valid evidence is the first *new* actual prospective source run using this implementation after owner-approved merge.
