# CORE-003 | X1 and cross-track references are not uniquely identified physical races

The original 27–30 October full-archive result [GitHub Actions 41125229029](https://github.com/Maremoo2/Betting/actions/runs/41125229029) reported **169 trotting database race records**. Examination of its exact derived JSON output (SHA-256 `33febe452c4f8275507fd92106d5ef812ffb1bf2782a70bb62045e2b7e418823`) found **15 `RIKSTOTO:X1_NR_` records**, with null/UNKNOWN country and multi-venue track strings:

- 27 October: seven `X1` references associated with `Bjerke/Axevalla`;
- 29 October: four `X1` references associated with `Bergen/Aby`;
- 30 October: four `X1` references associated with `Jarlsberg/Romme`.

These are **not independently verified as 15 distinct physical race events on one track**, so treating all 169 database records as 169 physical races overclaims source denominators.

Additionally, eight `RIKSTOTO:S5_NR_2026-10-28` source references have `country=SE` **but** combined `track=Solvalla/Bergsåker`. The conservative single-physical-track admission rule must flag these too, producing **23** unresolved multi-venue references in total. This is verified by the real [CI original archive run 41127284420](https://github.com/Maremoo2/Betting/actions/runs/41127284420). No manual removal or silent backfill is appropriate.

The corrected audit retains all **169 archive references**, distinguishes **146 single-track candidates** from **23 unresolved composite/unlocated references** and keeps those 15 in an explicit unresolved bucket. The *146 are candidates*, NOT independently independently-verified unique physical races; duplicates/cross-track mapping must be proven against provider race IDs. Counts and blocks are still reported for all 169 records for archive completeness.

The prior result 17 source-ready (all SE), 150 blocked, 2 before T−4, 0 PIT-certified remains true **for the 169 reference records**. These rates should not be presented as verified physical race coverage. PIT and Champion/BET authority remain OFF.

Related [CORE-003 #83](https://github.com/Maremoo2/Betting/issues/83) and [CORE-001/002 #89](https://github.com/Maremoo2/Betting/issues/89). No raw SQLite/provenance edits and no production policy change.
