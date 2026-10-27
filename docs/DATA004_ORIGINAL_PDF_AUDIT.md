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

**Not completed by this PR:** access to those 24 actual PDF bytes in the execution environment; historical row identity independently confirmed from rendered pages; 390 original-column values independently transcribed, ambiguity coded, and reviewed; running existing and candidate parsers against frozen gold; any deployment acceptance. A synthetic PDF fixture is used **only to test checksum/page-count/path rejection**, not to assert that a real source is correct.

Until independent source review and a separate acceptance PR, status is `HOLDOUT_GOLD_PENDING`, with `BET_BLOCKED` unchanged.
