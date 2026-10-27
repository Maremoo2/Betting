# DATA-004 | Offline historical-parser diagnostics (research only)

**Scope:** DATA-003B 60-observation diagnostic sample and 780 field audits. No Collector production parser integration, no V3.3.12 or BET changes.

## Locked inputs

Obtain the original files from the Betting Project/Library; **do not commit original programs, training labels, proprietary source payloads, or personal data to this repo**:

- DATA-003B_gold_standard_60.csv, expected SHA-256 \`3119c8d470618b54b62f06902e4ba215fe52b7d90ea4634524c4c97cd5904c93\`
- DATA-003B_field_validation.csv, expected SHA-256 \`6011524ea6a342604bbc63c2b977743f2dc6dc086b346196b748a7998445caf7\`
- DATA-003B_checksums.txt (contains the two SHA values above and reference hashes for reports)

Uploads named \`...(1).csv\` are accepted: the checker strips that download suffix when matching the checksum manifest. All 60 horse-block identities must already be VERIFIED by DATA-003B original-PDF transcriptions.

## Usage

\`\`\`bash
python -m hbi.data004_diagnostic \
  --gold 'DATA-003B_gold_standard_60(1).csv' \
  --fields 'DATA-003B_field_validation(1).csv' \
  --checksums 'DATA-003B_checksums.txt' \
  --output 'data004-development-only.json'
pytest -q tests/test_data004_diagnostic.py
\`\`\`

The checker aborts on an altered checksum, duplicate/missing assessment, unexpected stratification, non-VERIFIED row identity, or contradictory field/source provenance. It **never writes** to the HBI DB, the Collector store, Sheets or any wagering endpoint.

## Verified development-sample result (27 Oct 2026)

- 60 source rows; exactly 20 PARSED + 20 PARTIAL + 20 UNPARSEABLE; 13 fields per source row = 780 evaluations.
- Old parser (from frozen DATA-003B baseline): 407 CORRECT, 216 MISSING, 2 WRONG, 35 AMBIGUOUS_GOLD, 94 UNAVAILABLE_GOLD, 26 UNRESOLVED_PARSED_VALUE.
- Within already PARSED/PARTIAL TRAV_SPACED cases, anchored equipment extraction proposes 14 source-VERIFIED **shoes** and 14 **wagon** missing values; explicit positive-gallop matching proposes correction of two source-VERIFIED \`False\` errors. **30/30** proposals match gold, in this reused *development* sample.
- 26 \`gallop=False\` with unavailable gold are **not** counted as parser mistakes; never treat absent \`g\` as evidence of \`False\`.
- TRAV_JOINED, UNPARSEABLE and FOREIGN_FLAT are deliberately excluded. A \`kubug\` or \`gdk\` code is not decoded. The 12 joined-row cases and PDF column positions remain a separate layout research problem.
- These numbers **are not an estimate of general parser accuracy**, because 20/20/20 oversamples difficult rows and the same data were used to diagnose the patterns.

The JSON report MUST say \`DEVELOPMENT_ONLY_HOLDOUT_REQUIRED\`, \`holdout_verified: false\`, and \`production_parser_changed: false\`. Anything claiming DATA004 production readiness from the 60 rows alone is incorrect.

## Remaining acceptance gates

1. **Pre-register a disjoint holdout** of historical rows not among DATA-003B's 60, across multiple PDFs, dates, tracks and formats. Preserve source ID, original PDF SHA, page, horse-section, parser version, and selection algorithm. Freeze candidates before manually reading the outcomes/labels.
2. Transcribe new holdout truth independently from **original PDF bytes** (including row ownership and physical x/y columns). Independently verify original source checksum/byte availability. Diagnostic text and earlier parser outputs cannot substitute.
3. Run old parser, experimental candidate and layout fallback against that untouched holdout. Compare per-field precision, known error count, coverage and abstentions, stratified by format; report numerical denominators and any source ambiguity. Never interpret \`UNAVAILABLE\` as a correct negative.
4. Audit all newly proposed fields for false positives and inspect non-trav/nonstandard formats; require no new verified wrong values. Test repeated daily PDFs and history-section boundary cases.
5. Only then propose a **separate** Collector parser implementation PR with source-level acceptance criteria and full E2E integration tests. Scope that PR separately from frozen Betting probability/model/economic gates.

**Current decision:** DATA-004 DEVELOPMENT DIAGNOSTIC COMPLETE; HOLDOUT AND PRODUCTION INTEGRATION BLOCKED; BET_BLOCKED unchanged.
