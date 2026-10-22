# M7A.1 — independent semantic reference and historical parser validation

**Validation delivery: M7A.1_PASS. Parser/model readiness: BLOCKED. Recommendation: M7B_HOLD.** A delivery pass means the requested source-grounded comparison is complete; it does not mean the parser passes semantic extraction requirements or authorizes model use.

## Preflight and authority

PR #44 was merged by HQ at `66947366de056dba79a576abdfd7ed46e044b0f4`, now this task's main/base. Its reference head remains `1be33d7d01ffe6f282a6394e2c37c771c1ec324f`. All M7A and earlier reports/results remain unchanged.

Fresh checks of both repository trees/fetched branches, GitHub task-ID searches and connected Drive DATA-002/DATA-003 searches found **no independently identifiable versioned DATA-002 180-row delivery or DATA-003 60-row truth set**. Searches now also return our own M7A reports; those are not recovered DATA deliverables. Missing original deliveries are not assumed not to exist elsewhere. The available parser is the existing companion `collector/pdf_program.py`, commit `d57ec73370fffb25dee1444029744581073b2327`, file SHA256 `2ea5c70dfa76a2c8dbc358bbfcb97657efe1f831a5f799cb3790b9064a1ae64d`. It remains unchanged and is not asserted to be DATA-002.

Existing M5 rosters/labels, M6 `model_candidate`, M3 identity/PIT checks and M7A PDF provenance/audit are reused. M6 still explicitly excludes unvalidated history. No strategy, provider admission, model gate, workflow or production state is modified. This is not M7B implementation.

## New reference, independence and limitations

`tests/fixtures/m7a1-ground-truth-v1.json` is **M7A1_MANUAL_PDF_TRUTH_V1 / 1.0.0**, a new fallback selection, not DATA-003. It contains 60 distinct history observations: **20 per original PDF**, 17 target horse blocks, multiple printed track codes and historical dates in 2025/2026. The original DATA-002 PARSED/PARTIAL/UNPARSEABLE strata are unavailable; no fake 20/20/20 parser-status split is claimed.

Semantic cells were manually transcribed by **Codex from rendered original PDF tables**, with the original PDF text retained for exact source location, before running the existing parser against the frozen reference. No parser output, M7A diagnostic expectations or external official values supplied the expected semantic cells. This is assistant visual source review, **not a claim of independent human or second-reader sign-off**. HQ can audit the same pages using the render recipe. It is diagnostic and deliberately emphasizes difficult cases, not a representative sample of 1,605 rows or the backfill.

Reviewed source pages: Bjerke/Eskilstuna 1, 2, 3, 7; Solvalla/Åby 1, 6; Jägersro 1. Each record has original PDF hash/page, exact source line and line number, horse header, physical target race reference, observation time, all required semantic fields, raw codes, per-field confidence and ambiguity reasons. The table's printed track code is preserved, not silently expanded into a verified historical track identity. The source bundle is the already archived `tests/fixtures/m7a-pdf-validation.zip`; no original PDFs are duplicated.

Source conventions are deliberately conservative:

- Explicit positive placing -> integer; explicit zero -> `UNPLACED`, never a numeric rank or automatic disqualification.
- `k` with `gdk` -> qualification/approved trial, not ordinary competitive placing. Two such observations are included.
- Explicit decimal time -> seconds/km (`11,1` -> 71.1). `frd8a`, `5g`, `ug`, `vändg`, `it`, `br ag`, `dg a` and `kubug` are preserved; no numeric time is invented from these codes.
- `AUTO` requires an explicit readable `a` marker; ambiguous composite codes and absence of `a` remain `UNKNOWN`. **Twenty-five PDF start methods remain unknown.** No missing marker is converted to VOLT.
- Only affirmative source evidence supports flags. Absence is `NOT_REPORTED`, not false. Ambiguous disqualification codes remain unknown. Beautiful Disaster has explicit `Startgal, diskad.` evidence.
- PDF identity is `UNKNOWN` because the PDF does not print a stable registration. Separately verified ATG identities appear only in the official evidence layer linked by observation ID; they do not backfill the PDF reference or automatically establish PIT.

No separate immutable archive/large-file policy beyond the existing repository instructions, fixture conventions and `.gitignore` was found. New reference/report JSON files are bounded, and the new ATG ZIP is under 100 KB. They contain no credentials/account data. Raw history lines and preserved provider envelopes may include market columns; these are quarantined source evidence, never approved feature inputs. Original large PDFs/ZIPs are reused rather than committed again.

## Actual comparison: separate localization, structure and semantics

The actual local replay loads the reviewed existing collector parser by checksum, parses original PDF text, and compares its existing output fields with all 60 frozen references. It does not add semantic extraction logic.

- Original source localization: **60/60**.
- Parser history line found: **60/60**; no missing selected line.
- Correct horse/program-number/physical-race assignment: **60/60**; no selected wrong block. This is structural attribution, not stable horse identity verification.
- Observed incorrect extracted dates/race numbers: **0/60** for each.

| Field | Correct / scorable | NOT_EXTRACTED | AMBIGUOUS_SOURCE | NOT_APPLICABLE |
|---|---:|---:|---:|---:|
| Date | 60/60 | 0 | 0 | 0 |
| Printed historical track code | 0/60 | 60 | 0 | 0 |
| Historical race number | 60/60 | 0 | 0 | 0 |
| Distance | 0/60 | 60 | 0 | 0 |
| Start method | 0/35 | 35 | 25 | 0 |
| Placing/category | 0/50 | 50 | 8 | 2 |
| Numeric km time | 0/49 | 49 | 2 | 9 |
| Gallop flag | 0/14 | 14 | 1 | 45 |
| Disqualification flag | 0/1 | 1 | 8 | 51 |
| Qualification flag | 0/2 | 2 | 0 | 58 |

Each row totals 60. `NOT_EXTRACTED` stays in the scorable denominator and never receives credit. `UNKNOWN` source facts are `AMBIGUOUS_SOURCE`; unreported/inapplicable facts are excluded from the scorable denominator. No comparison of two missing values is called correct. The full `docs/M7A1_COMPARISON.json` records counts, denominators, per-observation expected/actual/status and critical findings. Raw track codes are compared exactly; unvalidated name expansion is not rewarded.

There are **271 missing required semantic values** across these diagnostic records. These are critical omissions, not 271 demonstrated wrong guesses. No current false numeric conversion of `frd8a` is observed because the parser supplies no placing/time at all. This cannot be presented as successful semantic extraction. Global omissions, global block correctness and error rates outside these selected 60 remain unmeasured.

## Mandatory regressions

| Example | Source-grounded outcome |
|---|---|
| God Only Knows | `NOT_REPRODUCED`: available combined PDF has header and five histories on page 7; no split history block. Existing source regression remains; synthetic cross-page locator tests are TEST_ONLY and not counted in 60. A different original failure version is still missing. |
| Single Lane | Row M7A1-013: `k`, `17,0`, `gdk`; qualifier, not numeric placing. Parser fails to extract qualifier status. |
| Eire | M7A1-017: `d` / `frd8a` retained; placing/time unknown, never 8 or a guessed time. |
| Custer | M7A1-003: `-` / `dg a`, explicit gallop narrative. DQ normalization not claimed without documented source-code meaning. |
| Goffa | Three explicit zero results remain UNPLACED; no automatic DQ flag. |
| Flying Finn | Five selected historical starts checked against the exact official races and stable ATG ID 788027, including 23 Sep victory / 71.1 sec/km. |
| Solvalla L9 | Existing real-source M7A regression proves V86-6 and V4-2 share `S1_NR_2026-10-21#9`; Åby L9 is a different physical field. No alias duplication. |
| Eskilstuna L5 | Existing M6 real-source test keeps all 12 monté conflict runners unresolved. No forced conversion to ordinary trot. |

## Official evidence layer: six starts, two horses

`tests/fixtures/m7a1-atg-results-v1.zip` preserves original timestamped ATG envelopes and hashes each member. Existing M7A Flying Finn evidence is copied with its original source archive hash; additional read-only requests use the existing AtgClient. No monthly archive search or crawler is introduced.

The deliberately small subset covers two wins, three seconds, an explicit gallop/DQ and one confirmed VOLT race:

| Horse / stable ATG ID | Historical official race | Official observation |
|---|---|---|
| Flying Finn / 788027 | 2026-03-04_5_9 | 1st, 72.8 sec/km |
| Flying Finn / 788027 | 2026-04-08_5_3 | 2nd, 72.7 sec/km |
| Flying Finn / 788027 | 2026-05-31_5_4 | galloped=true, disqualified=true, kmTime code `5`, no numeric placing/time fabricated |
| Flying Finn / 788027 | 2026-08-26_5_6 | 2nd, 72.8 sec/km |
| Flying Finn / 788027 | 2026-09-23_5_8 | 1st, 71.1 sec/km |
| Pure Ego / 793918 | 2026-02-25_27_8 | 2nd, 77.9 sec/km; official startMethod `volte` |

Six source-specific checks report `RESULT_VERIFIED`; none has a conflicting known PDF value. Ambiguous PDF values remain ambiguous even when ATG supplies an answer. Example: Pure Ego's PDF start method remains UNKNOWN while the separate official layer says VOLT. Flying Finn's `d`/`5g` is not changed into numeric placing/time using the official result. All raw source values and URLs are retained in the separate comparison layer. The historical results are retrospective labels, never target-race inputs.

Names alone are insufficient: exact date/track/race metadata, stable ID and pedigree are checked. Flying Finn is linked through the existing target-field proof for 21 Oct; Pure Ego uses the 24 Oct Jägersro field, number 6, ID 793918 and PDF sire Creatine/dam Restless. Target race results are not read. ATG observations are on 22 Oct: after Flying Finn's target but before Pure Ego's target. Neither fact automatically approves feature PIT or model admission. NO-specific official semantic coverage remains a limitation; the official subset is SE and is not a representative validation estimate.

## M7B contract proposal and decision

`docs/M7A1_HISTORY_FEATURE_CONTRACT.json`, version `0.1.0-proposal`, defines field datatype/unit, normalization, missing values, provenance/identity, cutoff/PIT, exclusions and allowed use. Proposed attachment is the existing M5/M6 history slot, not another store. All fields remain `RESEARCH_ONLY`, `model_eligible=false`; SHADOW_CANDIDATE/MODEL_ELIGIBLE are future gated vocabulary, never assigned here. Existing `HISTORY_FEATURE_CONTRACT_NOT_VALIDATED` remains enforced.

**M7B_HOLD:** source preservation and date/race-number extraction are technically reusable. Typed distance/time/placing/flags could eventually be useful, but the existing available parser does not extract them. Locate and review the actual DATA-002 delivery before creating competing extraction logic; otherwise define a narrowly scoped extension to the existing collector parser with separate validation. First settle qualification/result-code semantics, source-backed historical start method/track identity, NO result verification, stable history links and PIT/full-field requirements. An independent second-reader review of this new reference would strengthen confidence; it has not occurred and is not falsely claimed.

## Reproduction and hashes

Install `pip install -e '.[dev]'`. Reuse a read-only companion checkout at `d57ec73370fffb25dee1444029744581073b2327` (same reviewed parser as M7A).

```sh
python -m hbi.pdf_semantic_validation \
  --truth tests/fixtures/m7a1-ground-truth-v1.json \
  --truth-sha256 82ca3f9e043cfc76c672b7efe15efe9da93090387972c762f4e306ffdaf1e39d \
  --bundle tests/fixtures/m7a-pdf-validation.zip \
  --parser-path /tmp/collector-m7a/collector/pdf_program.py \
  --official-archive tests/fixtures/m7a1-atg-results-v1.zip \
  --official-sha256 f717e0ab2767abc436cadcf0ceecfbbe524233bb162db2ad1d6e71b9d3ebeabf \
  --output /tmp/m7a1-comparison.json
pytest -q
ruff check .
```

Actual terminal: **M7A.1_PASS**, recommendation **M7B_HOLD**, model_eligible **0**. Omitting official evidence produces PARTIAL, not a complete-delivery claim. CI tests compare the frozen reference against original PDFs and archived parser output; actual checksum-pinned external parser replay was separately executed locally. No synthetic data appear in the reference or official evidence. Mutated tests are explicitly TEST_ONLY.

Original PDF/source archive hashes and observations remain in every reference and the unchanged M7A evidence. Current file hashes/test evidence are in `docs/M7A1_EVIDENCE.json`; exact-head CI is recorded in the Draft PR. Rollback: revert this PR, preserving original M7A and production state.
