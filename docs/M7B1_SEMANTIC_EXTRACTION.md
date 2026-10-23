# M7B.1 — research semantic history adapter

**M7B1_PARTIAL / REVISE; HQ review only.** Semantic extraction is implemented and
validated on the specified diagnostic samples. Complete physical track resolution
and several source-code meanings remain unresolved. This is not model approval.
No strategy, provider, production, workflow or model-admission file is modified.

## Preflight and ownership

Development base is current main `697244a326095da63b4b9fbececf197e7a3061b1`.
HQ had merged #44 (`66947366de056dba79a576abdfd7ed46e044b0f4`) and #45
(head `09a12da439759f5700d6a781a258191a7738a17a`, merge = development base).
Existing M7A/M7A.1 reports, 60-row transcription and prior results are unchanged.
The original versioned DATA-002 180-row delivery and DATA-003 60-row independent
reference remain unavailable in the inspected sources; neither new set is
presented as a recovered DATA-003 delivery.

The external `Maremoo2/rikstoto-program-collector` owns PDF race/horse/header and
history-line discovery in `collector/pdf_program.py`, main
`d57ec73370fffb25dee1444029744581073b2327`. Its checksum-pinned implementation
is unchanged and invoked through existing `hbi.pdf_validation.load_parser`.
It currently supplies raw lines, date and historical race number, leaving the
requested semantic cells empty. No external parser is copied into Betting.

Betting's new `hbi.history_semantics` is a **record-level research adapter** over
those existing `past_starts`. It validates the raw header against the upstream
date/race, requires a unique table-prefix interpretation, and adds a separate
versioned semantic envelope without overwriting the collector record. It does
not locate PDF horse blocks, join historical identity or write a database.
`hbi.history_semantic_benchmark` reuses existing original-PDF, page/block,
whole-field routing, checksum and comparison components. Whole-field routing
checks printed assignment, not stable historical horse identity.

## Frozen evaluation and second control pass

Known set: unchanged M7A.1 60 source transcriptions, 17 horse blocks, three PDFs.
New holdout: 30 source transcriptions, six different horse blocks, zero raw-line
intersection with the known set. Before semantic implementation, the selection
was fixed to five histories each of the first two horses on X1 page 5 (Bjerke6),
S5 page 2 (Solvalla7), and S1 page 2 (Jägersro2). This covers 10 NO-target and
20 SE-target observations, multiple tracks, dates, decimal formats, zeros and
4g/8g special codes. It contains no assessable DQ/qualification cases; those are
covered only by the small known-set denominators, not claimed validated on holdout.

Holdout source transcription/lock commit precedes implementation. Implementation
and evaluator were frozen in `d9ae10d5ab06add0a5ec8410793af16b8246d845` before
first holdout evaluation. First results were committed in `ba5facb`; the exact
adapter/evaluator/codebook hashes and reproducible full-output hash are in
`M7B1_HOLDOUT_FIRST_EVALUATION.json`. **No adapter, codebook or evaluator change
was made after seeing holdout results.** Later tests only check the frozen output.

The transcriber and controller were the same Codex agent, not a human or blinded
independent reviewer. Truth was read from original rendered PDF tables, not
copied from semantic parser output. A separate source-reading pass checked all
30 holdout numeric/result cells against original PDF layout text before lock.
A further critical known-case pass reread X1 pages 1/2 (Custer, Goffa, Single
Lane, Eire), S5 pages 1/6 (Wingait Siw, Flying Finn, qualification), and S1 page 1
(Pure Ego). In particular `gal 300 kv`, `k ... gdk`, `frd8a`, `dg a`, zero,
`11,1a` and plain `17,9` remain consistent with the frozen source transcription.
No conflicting reference values were silently rewritten. This is a separate
Codex control pass, **not independent human sign-off** or a blind generalization
study. Neither sample is representative of all 1,605 lines or other archives.

## Measured field results

Counts are correct / assessable, not extraction over all rows. Unknown source
values and not-applicable values are separate, never credited as correct.
All assessable extracted values below have zero incorrect and zero missing;
coverage and extracted-value correctness are 1.0 within these denominators.
Full status counts and denominators are in `M7B1_FIELD_METRICS.json`.

| Field | Before, known | After, known | First holdout |
|---|---:|---:|---:|
| Date | 60/60 | 60/60 | 30/30 |
| Printed track code | 0/60 | 60/60 | 30/30 |
| Printed historical race number | 60/60 | 60/60 | 30/30 |
| Distance, m | 0/60 | 60/60 | 30/30 |
| Start method | 0/35 | 35/35 | 20/20 |
| Placing/category | 0/50 | 50/50 | 28/28 |
| Time, seconds/km | 0/49 | 49/49 | 28/28 |
| Explicit gallop | 0/14 | 14/14 | 4/4 |
| Explicit disqualification | 0/1 | 1/1 | 0/0, not assessed |
| Qualification | 0/2 | 2/2 | 0/0, not assessed |

Prior zeros mean NOT_EXTRACTED, not proven misinterpretations. Source localization
and printed horse/physical target-field assignment are 60/60 and 30/30. Critical
wrong-value or wrong-assignment findings in these evaluations: **0**. This does
not count unresolved source semantics as correct or prove unseen cases safe.

**Physical historical track identity is a separate metric.** Only 34/60 known
and 9/30 holdout codes have an unambiguous NO/SE name/country candidate in the
referenced register. The remaining 26+21 are explicitly ambiguous/unverified.
These 43 mappings are not verified provider IDs or independent historical-race
identity; no independent physical-identity accuracy gold is claimed. In
particular B/F/J/S are cross-country collisions and target country is not used
to guess. NO aliases BI/M/K/OA are retained as candidates until the cross-country
register is corroborated. This incomplete P0 field prevents a full PASS.

## Mandatory real-source cases and conservative limits

- Single Lane, X1 p2: `k 2140 17,0 gdk` becomes approved qualification, not an
  ordinary placing. A second qualifier is preserved on S5 p6.
- Eire, X1 p2: `frd8a` remains UNKNOWN_CODE for time/start method; not eighth,
  68 seconds/km or guessed automatic start.
- Custer, X1 p1: `dg a`, own `g fra start` and `ny gal` support gallop/AUTO;
  the entire DQ code remains unknown, not a guessed rank or automatic DQ.
- Goffa, X1 p1: zero is UNPLACED, not zero rank or automatic disqualification.
- Flying Finn, S5 p6: 23 September win and `11,1a` -> 71.1 seconds/km. Existing
  separate ATG chain verifies horse 788027, Solvalla race8; no identity is
  propagated into other rows. `5g` supplies a g marker, never 65 seconds/km.
- Pure Ego, S1 p1: `17,9` -> 77.9 seconds/km; missing a does **not** prove VOLT.
  Existing independent ATG evidence says VOLT for that race, retained separately.
- Solvalla L9 V86/V4 aliases still route to one physical field using the existing
  regression; different-track L9 remains separate.
- Eskilstuna L5 monté conflict remains blocked by the existing M6 test.
- God Only Knows source block is on X1 page7; split-block failure remains
  NOT_REPRODUCED. Existing synthetic page-break test is only TEST_ONLY.

The versioned codebook retains raw `frd8a`, `dg`, `br`, `ug`, `kubug`, `vändg`,
`5g`, `4g`, `8g`, `d` and `-` without pretending their full meanings are resolved.
An explicit own-event narrative may supply a gallop/DQ fact independently of an
unknown table code. Decimal times only are numeric; missing/compound times and
placing are never zero/null. No false gallop/DQ is inferred from absence.
Only explicit a supplies AUTO; no evaluated PDF supports an independently
justified VOLT extraction. Unknown method is an intended exclusion.

Primary Swedish code-index text was accessible through indexed primary-source
text, but the original URL returned a verification HTML page and its documented
CMS redirect HTTP403. **No binary verification of that code-index PDF is claimed.**
This limitation does not affect the verified original race-program PDF hashes.
A complete authoritative country/provider codebook remains required before
expanding semantics. This research adapter deliberately leaves uncertain codes
unresolved instead of decoding them to make coverage green.

## M5/M6 interface and temporal controls

`M7B1_HISTORY_FEATURE_CONTRACT.json` extends the existing proposal for
`model_candidate.inputs[].features.history`. Output carries raw collector record,
PDF/page/line/block and original codes, parser/codebook versions, source observation
time, unknown publication time, identity/result/PIT status and exclusions.
Raw lines may include historical market/prize text: they remain quarantined
evidence, never fundamental feature values. Official result labels are not read
by the semantic normalizer and do not overwrite the PDF truth.

Every new record is RESEARCH_ONLY, model_eligible=false, PIT=UNVERIFIED.
Future/same-day events and raw/upstream date/race conflicts are rejected.
Event-date screening is not PIT verification. Existing M5/M6 history admission
and HISTORY_FEATURE_CONTRACT_NOT_VALIDATED are unchanged; no automatic
attachment to training inputs or parallel datastore is introduced.

## Reproduce

Python 3.12, existing `pip install -e '.[dev]'`; no new dependency. From repo root:

```sh
python -m hbi.history_semantic_benchmark \
  --parser-path /path/to/rikstoto-program-collector/collector/pdf_program.py \
  --output /tmp/m7b1-new-report.json
python -m pytest -q
ruff check .
```

The output path must not exist; frozen reports cannot be overwritten silently.
The parser must have the exact SHA in evidence (wrong versions are rejected).
The full deterministic JSON includes every decision with PDF hash/page/raw line,
semantic status and exclusions; its first-run hash is committed, avoiding a
second 770KB report copy. CI uses checksum-verified originals and archived
collector records; **actual external parser execution was performed locally**,
not falsely claimed in CI. See evidence JSON and exact-head PR checks for results.

## Remaining decision / rollback

Recommend **M7B2_HOLD for model-feature integration** pending HQ review, authoritative
NO/SE code/track disambiguation and broader independent validation. Identity/PIT
research can be scoped separately, but no model admission follows this delivery.
Historical stable horse/race identity, full-field completeness, official NO/SE
result corroboration, feature availability before cutoff, and later time-based
OOS/calibration remain separate prerequisites. No probabilities or ranking exist.
Rollback is to close the Draft PR or revert its additive research files; existing
M1–M6 runtime, collector and frozen policies are unaffected.
