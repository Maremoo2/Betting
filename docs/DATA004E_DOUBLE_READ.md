# DATA-004E: independent second-read protocol (research-only)

The original 30-sample holdout is fixed at 10 PARSED, 10 PARTIAL and 10
UNPARSEABLE entries, with 13 historical fields each (390 cells). The existing
30-page DATA-004D blind visual-review packet was checked separately for
30/30 expected sample IDs, horse names, historical race tokens and 13 field
prompts. This **packet completeness** is not independent original-field gold.

## Review workflow

Two reviewers must each inspect the *original PDF* independently (not
the printed review packet as the sole source), confirm the horse/dated
history row and fill separate DATA-004C review CSVs with source rectangles.
Reviewers must not inspect the incumbent or candidate parser outputs, or
each other's review, before both are frozen. Preserve unresolved, ambiguous,
and unavailable cells as such. Never infer `gallop=False` or `dq=False`
from absent printed markers.

```bash
python -m hbi.data004_double_review \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --locators research/data004c-holdout-source-locators-v1.json \
  --source-root /private/unaltered-collector-artifacts \
  --review-a /private/reviewer-a.csv \
  --review-b /private/reviewer-b.csv \
  --output /private/DATA004E_double_read_diagnostics.json
```

The command rehashes the original 24 PDF programs, validates both complete
390-cell review schemas and compares literal source values/statuses/codes.
It reports missing reviews, duplicate/altered identities, reviewer-ID
collisions and disagreements for adjudication. **Even when 390/390 pairs
agree, `holdout_verified=false` and `production_parser_approved=false`.**
Matching reviewer declarations alone cannot establish real reviewer
independence or correctness of the original PDF interpretation.

The actual visual field transcriptions, a third-party adjudication of
conflicts, an accepted sealed private gold manifest, and a preregistered
incumbent-vs-candidate comparison remain pending. No data is silently
converted to a negative or parser promotion. No V3.3.12, A-WATCH,
BET-hardgate, betting, production parser, or settlement changes.
