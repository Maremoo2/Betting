# DATA-005Z | Research-only history/identity review ledger

**Prepared:** 30 October 2026 · **State:** `READY_FOR_PR_REVIEW`, NOT merged or CI-approved.

## Scope and exactly what is in GitHub today

- `Maremoo2/Betting` PR #69: DNT two-race program/history source extraction, **merged**.
- `Maremoo2/Betting` PR #70: pilot column alignment and fail-closed atomic CSV export, **merged** on 30 Oct 2026.
- DATA-005Z's subsequent field-level review and identity candidates: **not part of PR #69 or #70**, and not a production HBI history import. This handoff proposes a distinct, tightly bounded research-only addition.
- As inspected, repository `main` SHA was `beac22b4ccd8e7c9670c022345ee69dce1eab1a6` (another BET-001B3 merge has taken place); re-check before applying to a current branch.

## Proposed GitHub change (three files)

1. `research/data005z-pilot-history-evidence-v1.json`: derived evidence **metadata only**, from archived DNT and prior same-agent review outputs. 120 historical row keys, 24 candidate-only identities, 14 Swedish row review references, source SHA/capture labels, no raw PDF/HTML payloads.
2. `tests/test_data005z_research_ledger.py`: stand-alone fail-closed research-integrity tests; **does not import a runtime/model module** and is runnable by existing GitHub `pytest -q` workflow.
3. `docs/DATA005Z_PILOT_RESEARCH_INTEGRATION.md`: evidence levels, safety gates, reproducibility and limits.

**Explicitly excluded:** `src/hbi/fundamental.py`, `src/hbi/engine.py`, any importer, production DB/Sheets, models, Champion, score, staking and BET gates. Do not post these rows as `RESULT` or any canonical data event to GitHub issue #18: the Intelligence Bridge intentionally rejects canonical result/history events.

## Evidence reconciliation and reproducible checks

The input archives present here were read locally; **5/5 original source-response bodies SHA-256 matched the embedded capture manifest**. The two target program PDF source hashes match all 120 history source pointers, all 14 Swedish source pointers and all 24 identity candidates.

| Assertion | Result | Qualification |
|---|---:|---|
| Historical form row keys | 120 distinct | 60 Bjerke + 60 Momarken, not independent model data |
| Candidate program horse identities | 24 distinct | 12 + 12, **0 permanent registry IDs** |
| Foreign Swedish review rows | 14 joined 1:1 | 12 secondary matches, 1 partial, 1 startlist-only |
| Norwegian retrospective result labels | 104 | Same-assistant review; no accepted independent double-read |
| Missing URLs in consolidated Norwegian review | 23 | All recovered from the separate original 23-row review journal by exact race/horse/date **and** matching distance, finish, km time |
| Norwegian result URLs after restoration | 104 / 104 | **URLs are not archived result page hashes**; no new source attestations inferred |
| Norwegian trial/practice events | 2 | Must never become regular historical racing starts |
| UELN/individually issued permanent IDs | 0 / 24 | Internal SHA fingerprint is only a temporary matching key |
| Source publication time | Unattested | Capture UTC is not publication UTC |
| Independent double-review approvals | 0 | The same agent reviewed both original and secondary fields |
| Historical rows eligible for p(win) | 0 | Not promoted by PR or JSON schema |

Input source SHA-256 values are recorded in the JSON manifest's `input_file_digests`; the original source ZIP is referenced by full archive SHA-256 and archived Actions artifact ID. The metadata JSON has a stable digest, recorded in the package SHA manifest. No source-owned copyrighted PDF or HTML bodies are included.

## Open Åmål race, 13 September 2026, race 2

- **SV-02 / Stjerne Liam:** dated entry at #8, 2080m. `dg a` in the next DNT program, but no separately archived and readable first-party Swedish result confirms the per-horse disqualification.
- **SV-04 / Haugestad Lalla:** #11, 2080m; secondary sources support gallop/1.37,7, but the `8` printed finish and `gal` secondary classification are not reconciled by an official first-party result receipt.
- A candidate official results URL pattern exists on ATG, but the direct Åmål page was not accessible here, so **no upgrade** from secondary/partial status.
- The Swedish Sportapp provides first-party race-day and horse search functions; a reviewer with official source access should archive actual result bodies and verify per-horse values, ID namespaces and record timestamps before any status update.

Useful external source context: Svensk Travsport's own Sportapp navigation guide at `https://fraga.travsport.se/org/svensk-travsport/d/var-ar-sok-sportinfo-sa-fungerar-sportappen/`. A startlist with #8 and #11 is at `https://www.gratistravtips.se/amal/2026-09-13`, but it **is not the official per-horse result journal**.

## Gates before promotion and guardrails

1. Require registered official per-horse identity from DNT or issuer, with an exact source path and actual response evidence. Match name + pedigree + birth date/ID, inspect collision/aliases, do not derive UELN from the 64-character internal fingerprint.
2. Obtain a complete **source-owner result receipt** for the two Åmål rows with original text/body hash, observation time, track, race number, start number, finish/disqualification semantics and time.
3. Preserve source publication time separately from source observation time; where publication time is not known, record `UNKNOWN` rather than backdating.
4. Independent human reviewer must separately read source and adjudicate; same-agent secondary matches are diagnostic only.
5. A new, authorized task would still be needed to wire real history features into a PIT-safe fundamental Challenger. This PR provides **neither import nor promotion authority**.

## Test evidence and launch decision

- Local command: `python -m pytest -q tests/test_data005z_research_ledger.py` from extracted handoff root: **11 passed**, 0 failed/0 skipped, 30 Oct 2026.
- `python -m compileall -q tests/test_data005z_research_ledger.py`: passed.
- Ruff: **NOT RUN**, dependency unavailable in current local runtime.
- Full Betting repo Pytest / GitHub Actions on these new files: **NOT RUN**, because no remote PR/CI has been started for DATA-005Z.
- Existing `main`/PR #70 CI is not evidence for this uncommitted handoff.
- Promotion: **`HISTORY_MODEL_BLOCKED`** / **`BET_BLOCKED`**. Repo review status: **`READY_FOR_PR_REVIEW`**, not `APPROVED_FOR_MERGE`.

## GitHub authority and rollback

Repository `AGENTS.md` and `docs/DEV_WORKFLOW.md` require a specifically authorized GitHub branch, commit and draft-PR scope; this research package by itself is not that authorization. An authorized developer should create a fresh, isolated research branch from current `main`, add only the three files above, run `ruff check .`, full `pytest -q`, the focused 11 tests, and the existing research checks, and **stop at draft-PR** for separate HQ review. No direct push/merge to `main`. If rejected, rollback is simply removing the three newly added paths; no production state is changed.
