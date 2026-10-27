# DATA-004B | Verify original PDF bytes before visual holdout review

**Research-only. No production parser, probabilities, market, V3.3.12 or BET gates changed.**

This adds a second, stricter stage after DATA-004 metadata gate PR #56.

- Metadata stage verifies **30 preregistered entries** in 10/10/10 strata and **24 indexed programs** spanning seven original Actions artifacts. A 64-character checksum string alone is NOT proof.
- The new byte audit reads all **24 archived original PDF files** at the paths already frozen in `research/data004-holdout-prereg-v1.json`, recomputes SHA-256 from actual bytes, and compares real page counts against the existing source-evidence index. It refuses missing or substituted bytes; does not download or guess data.
- Only if all 24 pass can it emit **390 EMPTY field-review tasks** (30 observations × 13 fields) for later independent visual transcription. No parser values, original history lines or gold guesses enter the template.

## Run locally with original archived files

Extract the seven already identified original GitHub Actions artifact ZIPs to a source directory containing the relative `output/daily/...` paths shown in the frozen manifest. Do not rename or alter source PDFs.

```bash
python -m pip install -e '.[dev]'
python -m hbi.data004_original_pdf_audit \
  --manifest research/data004-holdout-prereg-v1.json \
  --source-evidence research/data004-holdout-source-pdf-evidence-v1.json \
  --source-root /path/to/unmodified/artifact-extract \
  --blank-ledger-output /path/outside/repository/DATA004_390_blank_review.csv
pytest -q tests/test_data004_original_pdf_audit.py
```

The output ledger **must remain private/off-repo** until source rights and review governance are established. Its `gold_status` is always `PENDING_VISUAL_REVIEW`; the empty cells and empty source-page/row locators are intentional. The CLI refuses overwriting an existing ledger.

## Actual original-source replay (27 October 2026)

After creating this draft PR, the seven original Collector Actions ZIP artifacts were
downloaded through the connected GitHub account (artifact IDs already recorded in
`research/data004-holdout-source-pdf-evidence-v1.json`). Their archived
`output/daily/.../meetings/.../full_program.pdf` entries were extracted without altering
their bytes. The extracted folders contained **32** distinct full-program PDFs in total;
the **24** PDFs referenced by the frozen DATA-004 holdout index were checked.

Actual Python `hashlib.sha256(pdf_bytes)` was compared against the source index, and
PyMuPDF/`fitz` was used to independently read each PDF's actual page count:

| Control | Result |
| --- | --- |
| Available original Collector artifacts | 7/7 |
| Holdout-referenced original PDF programs | 24/24 located |
| SHA-256 match against existing source index | 24/24 |
| Actual PDF page counts match source index | 24/24 |
| Unexpected source-byte/page-count mismatches | 0 |
| Independent physical horse-row/column evidence | **NOT verified in this replay** |
| Independent semantic field gold | **0/390 newly accepted** |

This is a **real source-byte replay**, separate from the synthetic CI fixtures. The
source-PDF originals and proposed private gold labels were **not committed** to GitHub.
This report measures exactly the source bytes and page counts; it does not substitute
for visual horse-row/column verification or independent 13-field labelling.
The new CLI's behavior is tested by CI; this actual-byte comparison was also performed
using a separate read-only verifier with the same SHA/page acceptance conditions.

**Still not completed:** independent original-page row ownership, 390 field transcriptions
with ambiguity states, frozen parser-vs-candidate comparison and production acceptance.
All betting gates remain blocked. A synthetic PDF fixture is used **only to test checksum/page-count/path rejection**, not to assert that a real source is correct.

Until independent source review and a separate acceptance PR, status is `HOLDOUT_GOLD_PENDING`, with `BET_BLOCKED` unchanged.
