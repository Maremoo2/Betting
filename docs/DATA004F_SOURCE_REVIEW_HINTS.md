# DATA-004F | Original PDF glyph anchors for blind field review

**Research-only. Read-only original sources. No accepted gold and no betting.**

DATA-004A–E established a frozen 30-row/10–10–10 sample, 24 SHA-checked
Collector original PDF programs, unique printed horse/history geometry and
a two-reader protocol. This step adds an **original-PDF review aid**, not a
new parser or independent truth.

## What changes

`hbi.data004_source_review_assist` must first repeat the DATA-004D
`verify_original_row_geometry` check on the actual 24 original
`full_program.pdf` source files. It then identifies each specific printed
historical row and extracts **literal PDF glyph substrings and exact PDF-point
rectangles** for unambiguous candidate fields. Every one of the 390 frozen
field prompts is retained, even when no source substring is extractable.

This never reads the incumbent or candidate parser values, copies hidden
old-parser labels, derives a betting score or produces a verified answer.
Every candidate is marked `PRINTED_TOKEN_HINT_UNREVIEWED`; absent/foreign/
ambiguous layouts remain `VISUAL_REVIEW_REQUIRED`. The output has no
mechanism for setting `holdout_verified=true` or accepting field gold.

It intentionally does **not** infer `gallop=False` or `dq=False` from
missing printed marks. It does not attempt to infer result categories or
start methods from neighboring numeric columns. Time-with-gallop codes,
foreign galopp formats, historical prize money, post/slot and composite
track identities must be resolved from the original visible PDF and its
field definitions by the independent reviewers.

## Independent original-source offline probe, 27 October 2026

The 24 archived original PDFs were re-hashed and page-count checked;
30/30 locked horse/history rows were already located by physical PDF
glyph geometry. A read-only prototype using those verified rows and
**no parser outputs** found **239 literal candidate tokens** across
390 source-field prompts. This is a count of automated navigation aids,
**not 239 correct field labels**:

| Field | Original-PDF glyph hints (out of 30) |
| --- | ---: |
| date | 30 |
| track | 29 |
| race_number | 30 |
| distance | 25 |
| start_method | 0 |
| result_category | 0 |
| placing | 25 |
| km_time | 18 |
| driver | 26 |
| shoes | 25 |
| wagon | 22 |
| gallop (positive printed token only) | 6 |
| dq (positive printed token only) | 3 |
| **All fields** | **239/390** |

The **151 remaining prompts are intentionally blank**. Some inferred
tokens, including equipment glyphs, still need visual column/meaning
verification; matching a short PDF snippet alone never proves a field
was interpreted correctly. The actual source-bound hint JSON remains
outside the repository with the original licensed PDF bytes.

**Accepted independent semantic gold remains 0/390.** This data is not
a representative performance estimate for all Collector history rows.

## Reproduce on the existing frozen sample

Extract all seven original Collector artifact ZIPs to a private root,
preserving the original `output/daily/.../full_program.pdf` paths.

```bash
python -m pip install -e '.[dev]'
python -m hbi.data004_source_review_assist \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --locators research/data004c-holdout-source-locators-v1.json \
  --source-root /private/unaltered-collector-artifacts \
  --output /private/DATA004F_original_pdf_hints_UNREVIEWED.json \
  --navigation-csv-output /private/DATA004F_source_review_navigation_390_UNREVIEWED.csv

pytest -q tests/test_data004_source_review_assist.py
```

The optional CSV sidecar has **exactly 390 unique sample/field prompts**,
with one `printed_token_hint_unreviewed` and its PDF-point rectangle where
available. Its `source_reading_accepted_gold` is always `NO`.
The exporter rejects duplicated sample IDs, missing fields, unsupported
statuses, promoted-gold claims and mismatched token counts; it refuses
overwriting an existing file. The sidecar is for navigation after reading
the original source, not a substitute for independent blinded transcriptions.

The output must stay **private/off-repo**, alongside the earlier
`DATA004C_blind_390_fields_UNREVIEWED.csv` and
`DATA004D_Blind_Visual_Review_30.pdf`. The CLI refuses to overwrite an
existing hint report.

## Acceptance boundary and next work

A real reviewer opens each original physical source page, confirms horse
and specific dated row ownership, reads each of the 13 printed columns,
and either transcribes a literal source value with a source bounding box
or records ambiguity/unavailability. A **separate** independent reviewer
must then do the same blind; DATA-004E compares their frozen private
CSV reviews and blocks any shared-reviewer overlap. Differences and
uncertain source columns require independent adjudication.

Only after the accepted private gold is sealed and a separate, unchanged
candidate-vs-baseline parser evaluation is completed should production
parser deployment even be considered. No V3.3.12, p(win), odds, A-WATCH,
WIN, provider live admission, strategies, staking, BET/WATCH/PASS, or
settlement behavior is changed. `BET_BLOCKED` remains in force.
