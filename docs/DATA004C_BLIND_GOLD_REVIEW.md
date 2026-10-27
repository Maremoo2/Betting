# DATA-004C — blinded source-grounded holdout review (research only)

This stage follows merged #56 (source-index gate) and #57 (original-PDF byte/page audit).
It **does not** modify or replace any of the original 30 holdout sample IDs, PDF
checksums, programs, statuses, parser code, model weights, V3.3.12, scores, odds,
BET hardgates, stakes, decisions or settlement.

## What is actually available

- **30 frozen** sample IDs: 10 original PARSED, 10 PARTIAL, 10 UNPARSEABLE.
- **24 original PDF** programs from seven existing GitHub Actions archives, SHA-256
  and page counts independently replayed on 27 October 2026.
- `research/data004c-holdout-source-locators-v1.json`: horse names, meeting, PDF page
  and history date/race tokens from the **existing, programmatically generated**
  private `DATA-004_holdout_30_source_mapping.csv`. It contains **no parser predictions
  or gold values**, and is **not independent visual verification**.
- A 13-field schema based on the original DATA-003B protocol:
  `date, track, race_number, distance, start_method, result_category, placing,
  km_time, driver, shoes, wagon, gallop, dq`.

## Create an unlabelled, blind review file

Extract the original seven Collector Actions ZIPs into a local directory containing
the unchanged `output/daily/.../meetings/.../full_program.pdf` paths. Keep the
reviews in a private directory **outside this public repository**. Never substitute
the old `DATA-002` parser output as ground truth.

```bash
python -m pip install -e '.[dev]'
python -m hbi.data004_gold_review \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --locators research/data004c-holdout-source-locators-v1.json \
  --source-root /path/to/unaltered/collector-artifact-extract \
  --blank-output /private/DATA004C_blind_390_fields.csv
```

This command **reopens and hashes all 24 actual PDFs**, checks their page counts,
refuses missing or altered bytes, and writes exactly 390 `PENDING_VISUAL_REVIEW`
cells. No `parser_*` or `parsed_*` field is exposed. It refuses overwriting an
existing review.

## How to review each field

Open the actual rendered PDF on the recorded page and locate the horse header,
history date and race number. The earlier text-based locator merely speeds up
navigation; **confirm horse-row ownership visually before filling any field**.
For each cell, record:

- `source_pdf_page`: the referenced **physical** PDF page (1-based).
- `visual_row_locator`: PDF points `x0,y0,x1,y1`, describing the exact
  original row or column supporting the assertion (positive rectangle).
- `row_identity_visual=CONFIRMED`, and an independently acting `reviewer_id`.
- `gold_status=VERIFIED` with the exact printed `gold_value` and
  `evidence_code=PRINTED_CELL`. The original source's codes/units must be
  preserved; do not silently normalize obscure codes.
- For **explicitly evidenced** negative gallop or disqualification, use
  `gold_value=False` and `evidence_code=EXPLICIT_NEGATIVE_MARK`. **Absence**
  of a gallop/DQ mark does not justify a false negative.
- For ambiguous joined/foreign layouts, `gold_status=AMBIGUOUS`,
  `gold_value` blank, `evidence_code=AMBIGUOUS_LAYOUT`, and a specific reason.
- For a genuinely absent field, `gold_status=UNAVAILABLE`, blank value,
  `evidence_code=NOT_PRINTED` (or `FOREIGN_FORMAT_UNRESOLVED`), and a
  concrete reason. An unavailable cell is **not** a verified negative.
- Keep unresolved cells `PENDING_VISUAL_REVIEW` with no guessed value or
  unsupported attestation.

The 30 rows can include race history on foreign or composite meeting programs.
Do not equate the composite meeting ID with an independently proven physical
track/horse identity.

## Validate private review structure

```bash
python -m hbi.data004_gold_review \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --locators research/data004c-holdout-source-locators-v1.json \
  --source-root /path/to/unaltered/collector-artifact-extract \
  --audit-review /private/DATA004C_blind_390_fields.csv

pytest -q tests/test_data004_gold_review.py
```

The validator rejects missing/duplicate field pairs, modified sample IDs,
wrong program SHA or page, columns carrying parser values, unlocated or
unattested reviews, ambiguous/unavailable cells with asserted values,
and unproven `gallop=False`/`dq=False` observations.

**Security and independence boundary:** a well-formed CSV is *not proof* that
a reviewer actually looked at the original page or that the values are
correct. Even a fully self-attested 390/390 CSV returns
`REVIEW_ATTESTED_EXTERNAL_ACCEPTANCE_REQUIRED` and `holdout_verified=false`.
A separate independent visual adjudication / freeze-and-hash approval
and a separate old-vs-candidate blind comparison are required for DATA-004
acceptance. No training, calibration, or bets are authorized by this PR.

## Prioritized next acceptance checks

1. Independently visually inspect and record original-page ownership and all
   390 field statuses; perform explicit second-reader adjudication for
   ambiguity/foreign or column-joined examples.
2. Seal accepted private gold file with source SHA and field-review provenance;
   preserve the review trail and prior frozen manifest unchanged.
3. Replay **unchanged** incumbent and candidate parser against that sealed gold
   without re-tuning; publish stratified denominators, verified new wrong values,
   coverage, abstentions, and unresolved cases. Separate parser correctness
   from any predictive or economic betting claim.
4. A later, separately authorized Collector parser PR may be considered only
   if independent holdout evidence and regressions justify it. No automatic
   deployment or BET gate promotion.
