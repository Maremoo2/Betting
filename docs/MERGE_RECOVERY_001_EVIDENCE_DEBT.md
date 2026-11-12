# MERGE-RECOVERY-001 | Historical evidence debt (not a replacement)

**IRRECOVERABLE_HISTORICAL_EVIDENCE** as of 2026-11-12.

Original authentic source run: https://github.com/Maremoo2/Betting/actions/runs/41518035718.
Original artifact: core003-pilot-state, ID 13176561174. Upload success 2026-11-02T20:19:04Z, job 125526524026, retention 7 days. Uploaded artifact ZIP size 7,332,519 bytes. Inner original SQLite: data/core003-pilot.sqlite. Expected SHA-256: 60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0.

Direct original artifact-id recovery returned HTTP 404. Surviving original run artifacts core003-pilot-report-41518035718 and bet-mvp-shadow-41518035718 contain no original SQLite; no other verified byte-identical authoritative backup with the pinned SHA was identified. Never synthesize replacement bytes.

## Distinct mandatory gates
The original historical replay step remains in .github/workflows/ci.yml, unchanged, mandatory and failing. It may not be skipped, removed, replaced, weakened, renamed PASS or assigned a new expected SHA without a separate explicit HQ change in release policy.

A new independent gate in .github/workflows/merge-recovery-authentic-replay.yml verifies the separate authentic 2026-11-12 Collector ZIP SHA-256 23871090f75ded32829fbc239ca6f1bae8be7d5784cc0f67c650a9aaeef639f3. It imports 30 NO/SE races and 321 real starters twice into a fresh SQLite, checks original PDF/starts full-field, source journal and idempotence, fails closed on retroactive model calculation and checks an immutable transferred SQLite with an independent runner. New state retention is 90 days, but that is not permanent PIT storage.

**This new replay can never prove the 2026-11-02 state was recovered.** It supports a future HQ decision about baseline/evidence debt; current merge policy remains NO-GO.

## Registry gap
DNT Sportssystemet and Svensk Travsport Sportappen are respective official horse registration systems. The CLOUD-RUN-006 candidate adapter joins genuine original registration fields from 12-Nov Collector ZIP to existing HBI runner identities with original byte SHA, rejects TMP/unknown and conflicting identities, and preserves source traceability. No verified public machine-access registry endpoint, independent original registry source extract, right to bulk copy, or cross-provider permanent mapping is available to this implementation. There are 0 independently attested permanent IDs; no Champion betting permission or prospective PIT.

MODEL=V3.3.12_FROZEN | PIT=BLOCKED | AUTO_BET=false | AUTO_MERGE=false.
