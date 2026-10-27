# DATA-004D | Original-PDF physical horse-row verification

**Research-only. Does not accept a gold field, change a parser, or authorize a bet.**

This stage follows DATA-004 #56–#59. Metadata-only checks and substring
horse-name matches on PDF pages are not enough. `hbi.data004_row_geometry`
reopens all **24 archived original full-program PDFs**, checks SHA-256 and page
counts against the frozen source index, and independently finds:

1. One unique large-print, left-margin horse heading with the expected name.
2. Exactly one printed historical `dd.mm.yy-race_number` token **below that
   heading and before the following horse heading** on the frozen source page.

The output records PDF-point rectangles for the horse header, physical horse
section, and dated history token. No source history prose or parser values
are copied into the report. Source text or geometry ambiguity is **fail closed**.

## Reproduce with original source bytes

The original seven Collector Actions ZIPs should be extracted to a private
source root retaining the frozen `output/daily/.../full_program.pdf` paths.
These originals are not committed to the research repository.

```bash
python -m pip install -e '.[dev]'
python -m hbi.data004_row_geometry \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --locators research/data004c-holdout-source-locators-v1.json \
  --source-root /private/unaltered-collector-artifacts \
  --output /private/DATA004D_source_geometry_30.json

pytest -q tests/test_data004_row_geometry.py
```

## Original-source verification, 27 October 2026

On the frozen 30 rows, a separate read-only run with actual original-PDF bytes
found 30/30 unique physical horse headers (including source-header typography)
and 30/30 unique historical date/race tokens inside those horse sections.
This is *source-location evidence*, not independent visual 13-field gold.

- 30 candidates remain unchanged: 10 PARSED, 10 PARTIAL, 10 UNPARSEABLE.
- 24/24 original PDF SHA-256 digests and page counts match source records.
- 30/30 printed header/date-race relationships are unique in those source pages.
- 0/390 semantic gold-field cells independently approved by this gate.
- `holdout_verified=false`, `production_parser_approved=false`,
  `BET_BLOCKED` unchanged.

The positive source-row result is conditional on the existing preregistered
navigation dates/pages; it does not measure general parser accuracy, and is
not independent manual reading of the 13 fields. Where a different printed
layout cannot be verified, the gate abstains rather than generalizes.

## Next acceptance stage

An independent reviewer must inspect the original rendered row and all printed
field positions, record exact literal field labels with their source bounding
boxes, and adjudicate foreign/merged layouts. Only after the resulting private
390-cell fasit is checked independently and sealed should the unchanged
incumbent and candidate parsers be evaluated. No parser deployment or betting
authorization is part of this work.
