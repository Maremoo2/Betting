# Acceptance: 2026-10-08

Status: PASS, retrospective January acceptance. No POST files opened by the engine; no claims of blind January validation.

## Frozen register

- Source: January 2026 V2 crawler, weekly PRE ZIPs W01-W05.
- Original full PRE SHA-256: `99284fd7f019b30c86f467a3fff8b714abc3dc0f077953c87416b18a591537b5`.
- Engine configuration hash: `fdbd9161ecebf0ae470d71ff1add6e87d67f45f8f89e433943dace892994bb56`.
- PRE_MASTER SHA-256: `42a641323d375c55a63cdd0214e3b8ec1ee8184b4f885d1f685f6223760e5fcb`.
- Local output: `research-local/pre-winner-engine-v1/january-final/PRE_WINNER_BULK.zip`.
- Original input files remain unchanged. No new W06-W40 collection was started.

## Counts

544 accepted races, 31 calendar dates, 104 meeting-days; 5,771 distinct active race/horse pairs; 7,271 race/horse/pool observations. 333 scratched runner records excluded. No race conflicts, schema rejections or duplicate source records.

| Timing class | Observations | Distinct races in class |
| --- | ---: | ---: |
| PRIMARY | 965 | 92 |
| SECONDARY | 361 | 35 |
| EXCLUDE_DIAGNOSTIC | 5,945 | 452 |

A race may occur in multiple timing classes; the class race counts are not additive. Coverage concerns the accepted archive, not every scheduled race.

Exclusive signal totals: NONE 5,682; MOD_POS 551; MOD_NEG 474; STRONG_POS 265; STRONG_NEG 133; EXTREME_POS 94; EXTREME_NEG 72. These include diagnostic observations and are not betting recommendations.

## Invariance and source checks

W01 alone: 78 races, 1,020 observations. Independent CLI processes for W01 and W01-W05 produced identical W01 rows in every PRE_MASTER column, including IDs, probabilities, labels and hashes.

Independently recomputed full active-field inverse-odds and share normalization from raw PRE JSONL with `math.fsum`; matched probabilities, delta and R within 1e-12:

| Horse / race | Product | Delta | R | Signal | Timing |
| --- | --- | ---: | ---: | --- | --- |
| Cogburn / Bjerke Jan 8 L1 | V4 | +12.3675 pp | 1.268031 | STRONG_POS | SECONDARY, 76 s |
| Klaas B.R. / Jarlsberg Jan 1 L3 | V64 | +11.1471 pp | 1.713947 | EXTREME_POS | PRIMARY, 31 s |
| Ramstad Stjernen / Jarlsberg Jan 1 L6 | V4 | +5.3816 pp | 1.309685 | STRONG_POS | EXCLUDE_DIAGNOSTIC |
| Ramstad Stjernen / same race | V64 | +5.1575 pp | 1.296789 | STRONG_POS | EXCLUDE_DIAGNOSTIC |

The last example receives dual positive consensus within its diagnostic cohort; it remains excluded from primary evidence. Cogburn is not EXTREME because its R does not reach 1.50.

Output manifest hashes verified. Installed `pre-winner --help` verified. Ruff passes. Regression tests cover exclusive AND classification, batch invariance, duplicate/conflicting races, invalid inputs, scratches, cohort boundaries, multipool evidence, POST isolation, hashes and immutable output.

## Next stage

v1 is frozen for future PRE processing. Future bulk collection and POST evaluation remain separate steps; freeze PRE registers before opening future outcomes. January data already had a previous POST crawl, so these acceptance figures establish pipeline consistency, not prospective predictive value.
