# P0-PROSPECTIVE-LEDGER-002

CORE-003 exports the existing Research Ledger after DEV-009 and retains it as a research-only Actions artifact. The export uses the current original cohort, CORE-003 report and Collector handoff even when DEV-009 publishes only a source diagnostic. Current observations are run-scoped; cumulative benchmark records keep their existing denominator and scoring rules. Unavailable cumulative counts remain unknown. The workflow adds no provider calls and writes no database.

## Original replay

[CORE-003 run 43393447156](https://github.com/Maremoo2/Betting/actions/runs/43393447156) provided a verified Collector import for `RIKSTOTO:F3_NR_2026-11-13:1`, followed by `COLLECTOR_RESEARCH_MODEL_GATE_NOT_VERIFIED`. DEV-009 produced `DOWNLOADED_ORIGINAL_INTEGRITY_FAILED`.

| Metric | Current run before | Isolated replay after | Archived before and after |
| --- | ---: | ---: | ---: |
| Physical races in ledger | 0 (no artifact) | 1 | 89 |
| SHA-verified model originals | — | 0 | 53 |
| Complete active model fields | — | 0 | 39 |
| Same-freeze WIN | — | 0 | 36 |
| Verified official outcomes | — | 0 | 32 |
| Scorable pairs / triples | — | 0 / 0 | 32 / 31 |
| Blocked with primary reason | — | 1 | 57 |
| PIT certified | — | 0 | 0 |

| Original | Artifact | Member SHA-256 |
| --- | ---: | --- |
| Collector handoff | 14021994512 | 6e40d7c48f1501194a9e8f30b0de9623ddeaa491faa8304de179fbc172a769e4 |
| CORE-003 report | 14022641211 | 3e45dfc6e23f4d1fa753fb25e21c12758e51ee46f647b5538670b152cd338f27 |
| Cohort index | 14022760818 | 62beae888f4ae48516f1a85b4f9843cda78324f121afd95f583c0ededade2bb5 |
| DEV-009 diagnostic | 14022641185 | 6f5336b19bb286561b67f1754b98e6a1934f3bdb29853f0cf88002d50d680286 |
| DEV-011 manifest | 14022860566 | 7173c1dae556e67b3720b74e6728073876e89e31336f356f727da4073b81fe4e |

ZIP digests matched GitHub metadata. Running the isolated current export twice produced identical SHA-256 `d6830db6e4739bc298bc8db644f1986b6a768169dee4a0db3a5fcb3872637e32`. Replaying the 89-race original `13361697131` via extracted directories preserved ledger SHA-256 `2df3b56cff7220b0b5f137ecc4fd917cfdc9b3b089e4b7317805eecbb7681da8`. The later original `13364215238` reproduced 34 pairs / 33 triples. All 51 model references shared across the two snapshots preserved their probability vectors. The two other references point to independently archived pre-cutoff freezes selected by the existing benchmark policy.

Targeted tests cover blocked, failed, verified, missing and tampered current members, repeatable import, and result revision isolation. 26 passed, 1 skipped. Ruff passed on the changed Python files. These are historical original replays. The draft workflow is not deployed, and no future race has yet verified it in ordinary operation.
