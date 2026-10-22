# M7A — historical PDF validation (research only)

Status: **M7A_PARTIAL / READY_FOR_REVIEW**, not permission to implement M7B.
Base Betting `840d255cbdad75ebb6c39e9ede0c0eb90cf12c34` includes merged M5 #42 and M6 #43. No model, decision, provider admission, production workflow or betting rules changed.

## Existing work and reuse

- The existing collector parser is `collector/pdf_program.py`, callable `parse_extended_pdf(text, meeting_id, date, url, captured_at, track)`. First implementation `efe3b91`, later fixes include `831ccb3`, `ec96d15`, `ac92b83`, `5efcf33`. Reviewed collector main: `d57ec73370fffb25dee1444029744581073b2327`. File SHA256 `2ea5c70dfa76a2c8dbc358bbfcb97657efe1f831a5f799cb3790b9064a1ae64d`.
- Its output is `races[].race`, `entrants[]`, `past_starts[]`, raw horse sections and raw history lines plus QA `REVIEW_REQUIRED`. It recognizes dated history lines and historical race numbers; it does **not** implement historical result semantics. Most history fields are deliberately null. It removes page footers and joins extracted pages; page numbers are not retained in its original output.
- No repository file, available branch history/documentation or connected Drive search result identified a separately delivered **DATA-002** implementation/output/schema or **DATA-003** independently annotated 60-entry truth set. This does not prove they do not exist elsewhere. The collector parser is identified by code/hash, **not asserted to be the missing DATA-002 delivery**. Search scope: both local repository trees and fetched remote branches/history; GitHub searches for the task IDs; Drive searches DATA-002/DATA-003 and named program tracks. Drive track searches returned ledgers, not original PDFs or annotation files.
- M3 `fundamental_view.py` retains UNVERIFIED_SOURCE history, prior-date checks and conservative identity attribution. M4 `historical_truth.py` supplies independent-result verification and readiness vocabulary. M5 `backfill.py` imports canonical rosters and separates retrospective labels from PIT features. M6 `model_dataset.py` attaches `HBI_RACE_MODEL_CANDIDATE_V1` to M5 records and explicitly blocks unvalidated history; `swedish_identity.py` supplies retrospective ATG identity evidence. These remain unchanged.
- This PR adds an **audit harness**, not another parser. It invokes only the exact reviewed external collector parser, preserves document/page/line evidence and checks one independent official result. No historical data are imported as model features.

## Original sources, independently preserved

All three requested original programs were found in existing GitHub release archives. Only these daily examples were retrieved; no monthly backfill was sought or recollected.

| Program | Release asset | Parent ZIP SHA256 | PDF SHA256 |
|---|---|---|---|
| Bjerke/Eskilstuna 20 Oct | [657061413](https://api.github.com/repos/Maremoo2/rikstoto-program-collector/releases/assets/657061413) | `a91c6d2147be18202a80423d1c1e9d32c3acdfca5d234de0dfe6bf28ae0f4981` | See bundled metadata/evidence |
| Solvalla/Åby 21 Oct | [657344961](https://api.github.com/repos/Maremoo2/rikstoto-program-collector/releases/assets/657344961) | `4fe7d2a4c4bc86917484c19d1fb00f22a76c0f376ab94e727a895fe194f3a680` | See bundled metadata/evidence |
| Jägersro 24 Oct | [657066047](https://api.github.com/repos/Maremoo2/rikstoto-program-collector/releases/assets/657066047) | `c34d97544875b6b10bdfffe3b0559ff6e240584c46442e585c8e25153454a3de` | See bundled metadata/evidence |

Downloads matched the archived release asset digests exactly. `tests/fixtures/m7a-pdf-validation.zip` contains the original three PDF byte streams, their archive/member references and archived NO/SE canonical starts responses. It is a **derived subset**, not the original ZIP. Its SHA256 is `1d4108180de1a191a3df502fde0e2ff4d2b74fc3f3b6eee30b701a18cb9e81a9`. Metadata separately hashes every original PDF and each included metadata file. Original PDF print times, race dates and crawler observations remain distinct; no print time is promoted to publication proof.

## Actual replay and coverage

| Program | Pages | Race sections | Horses | Raw history lines | Complete-field routing |
|---|---:|---:|---:|---:|---:|
| Bjerke/Eskilstuna | 8 | 7 | 83 | 415 | 7/7 |
| Solvalla/Åby | 8 | 8 | 92 | 460 | 8/8 |
| Jägersro | 12 | 12 | 146 | 730 | 12/12 |
| Total | 28 | 27 | 321 | 1,605 | 27/27 |

The reported counts reproduce with the existing parser, and every emitted raw history line is found at a unique PDF page/line. Complete-field names/numbers also agree with independently structured `/starts` responses. **Neither count agreement nor source-line location measures historical-field accuracy or detects every omitted/unrecognized source row.** No claim of global recall, horse-block accuracy or 100% parsing accuracy is made.

Both combined programs retain `DUPLICATE_RACE_IDS`: the same printed number occurs at different physical tracks. Whole-field routing distinguishes them without rewriting the source. For example, Solvalla L9 routes to `S1_NR_2026-10-21#9` and Åby L9 to `S2_NR_2026-10-21#9`. Solvalla L9 has both V86-6 and V4-2 printed on **one field**. Product-leg aliases are not additional races. Routing by names/numbers is only source-field reconciliation, **not stable horse identity proof**.

### Diagnostic field measurements

DATA-003's independent stratified 60 entries are unavailable: **accuracy against that truth set is NOT_RUN**, not PASS.

A separate agent-transcribed, nonrepresentative diagnostic uses five printed history lines each for Custer, Goffa, Single Lane, Eire, God Only Knows and Flying Finn (30 total). The expected dates/race numbers are in `tests/fixtures/m7a-diagnostic-dates.json`; they are **PDF transcription checks, not official result truth or a substitute for DATA-003**.

| Field | Diagnostic outcome |
|---|---|
| Historical date | 30/30 matches the diagnostic transcription |
| Historical printed race number | 30/30 matches |
| Track, distance, placing, kilometre time | 0/30 populated for each; conservatively withheld, not 30 incorrect guesses |
| Qualification vs ordinary start | No structured distinction; Single Lane's `k ... gdk` remains raw/unresolved |
| Whole-dataset missing starts, wrong block, wrong semantics | Not measurable without independent annotations |

No representative error rate or confidence interval is claimed from this diagnostic selection.

### Named regressions

- **God Only Knows:** five histories located on page 7 of the combined original. The preceding page ends another horse and page 8 begins another race. The reported history-block split is **not reproduced in this version**; do not claim a sideshift fix. A different original/extraction version demonstrating the failure is still required.
- **Single Lane:** `Ro 29.09.26-13|66 k 2140 17,0 gdk 0'` is preserved; no numeric placing or ordinary-start classification is fabricated. Lack of a qualification field blocks start-count/model use.
- **Eire:** `Ax 19.07.26-10|66 d 2140 frd8a ...` remains a raw code; `placing=None`. No numeric interpretation of `frd8a`.
- **Custer:** `B 12.09.26-3|1011 - 2100 dg a ...` retained, no inferred numeric placing. Galopp/disqualification semantics still require documented code meanings/official result.
- **Goffa:** three zero-placement lines are retained with `placing=None`; zero is not converted into disqualification. This does not independently establish every result's official semantic meaning.
- **Flying Finn:** separate official check below.
- **Solvalla L9:** V86-6 and V4-2 are one physical race; another track's L9 remains distinct.
- **Eskilstuna L5:** existing M6 real-source regression still requires its 12 monté runners to remain unresolved. M7A does not relax that control.

## One independent official result chain

The selected PDF says Flying Finn, Solvalla 23 Sep 2026 race 8, number 1, place 1, 2140m, `11,1a`.

Existing read-only `AtgClient` fetched exactly the Solvalla calendar references and selected races for 23 Sep and target 21 Oct. The archived envelopes are in `tests/fixtures/m7a-flying-finn-atg.zip`, SHA256 `8e0013ed4dbacb638e354807433cec4ab53a8412c957372279d1c5966bed01fc`; its manifest pins every original envelope file. These hashes refer to archived envelope bytes, not raw HTTP response bytes.

- [Historical official race](https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-09-23_5_8): Flying Finn number 1, **horse.id 788027**, place 1, kmTime `{minutes:1,seconds:11,tenths:1}` = **71.1 seconds/km**.
- [Target field](https://www.atg.se/services/racinginfo/v1/api/games/vinnare_2026-10-21_5_9): Flying Finn number 5, **same ID 788027**, same sire Readly Express and dam Railin. PDF biography agrees. The target race's result is never used by this verifier.
- Exact calendar date, track, country, discipline, race number, stable horse ID and pedigree are checked. Wrong race, horse or result mutations are rejected.

This is **one RESULT_VERIFIED chain**, not an independently validated dataset. ATG was observed on **22 Oct 2026**, after the target race. Retrospective identity/label corroboration does not establish pre-target identity availability or approved feature PIT. Model eligibility stays false.

## Reproduction

Python 3.12; install project development dependencies (pypdf is a test/audit dependency):

```sh
pip install -e '.[dev]'
# Read-only checkout of the existing companion repo at its documented commit:
git clone https://github.com/Maremoo2/rikstoto-program-collector.git /tmp/collector-m7a
git -C /tmp/collector-m7a checkout d57ec73370fffb25dee1444029744581073b2327
python -m hbi.pdf_validation \
  --bundle tests/fixtures/m7a-pdf-validation.zip \
  --sha256 1d4108180de1a191a3df502fde0e2ff4d2b74fc3f3b6eee30b701a18cb9e81a9 \
  --parser-path /tmp/collector-m7a/collector/pdf_program.py \
  --parser-sha256 2ea5c70dfa76a2c8dbc358bbfcb97657efe1f831a5f799cb3790b9064a1ae64d \
  --result-bundle tests/fixtures/m7a-flying-finn-atg.zip \
  --result-sha256 8e0013ed4dbacb638e354807433cec4ab53a8412c957372279d1c5966bed01fc \
  --output /tmp/m7a-validation.json
pytest -q
ruff check .
```

Actual terminal output: `M7A_PARTIAL`, `model_eligible: 0`, source counts 83/415, 92/460, 146/730. Detailed output keeps PDF hash, original line, page, horse block pointer, observation timestamp, historical date, unresolved identity/feature/PIT status, and the one separate official result proof. The harness does not create model features, probability scores or decisions. CI tests use archived parser output plus original PDFs; **actual parser replay is a separate locally executed command**, not misrepresented as CI replay.

## M7B recommendation: M7B_HOLD

Do not implement M7B yet. Obtain the versioned DATA-002 code/output/schema and independently annotated DATA-003 60-entry diagnostic, plus the original God Only Knows failure version. Verify qualification and country-specific result code meanings against original official results, including ambiguous codes. Expand source-grounded checks for missing starts, wrong blocks and ambiguous dates/track abbreviations before approving a feature definition.

Minimum future adapter changes, once validated:

1. Attach original document hash, page/line and block reference to existing parser observations; preserve raw codes and missingness.
2. Route composite product sections to existing physical race identities with full-field source evidence; record product-leg aliases separately. Never deduplicate by printed race number alone.
3. Map only documented parser fields into M5/M6's existing history contract; keep qualifications, unplaced, disqualified, galopp and unknown codes distinct. Do not build a parallel parser/store.
4. Carry identity verification, official result verification and feature-PIT verification as separate states. A retrospective result can be a label; input features require proven/conservatively justified availability, race timing and identity evidence. PDF date alone and M6 retrospective matching are insufficient.

Current M5/M6 `HISTORY_FEATURE_CONTRACT_NOT_VALIDATED` remains in force. No candidate is upgraded. Revert this PR to roll back the audit tools/fixtures; production state is untouched. CI/test evidence and exact PR head are recorded in the draft PR.
