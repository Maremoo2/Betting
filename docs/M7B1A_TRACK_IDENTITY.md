# M7B.1a — historical track identity verification

**M7B1A_PARTIAL / REVISE.** Seventeen observation-specific track identities are
now source-bound; this is not an identity/PIT/model admission or a global alias map.

## Actual preflight / base

PRs #44, #45 and #47 were all merged by HQ when this task began. #47's head remains
`13a37d9df26a14d487314ac5a953e4e08c99411e`; its merge/current main is
`f850f51f6c3ae9d20bbcab31090ab0c35f47d3f1`, the base of this branch. There is no
unmerged dependency or copied unfinished implementation. The earlier #47
closeout saying Draft/unmerged was accurate then and has been superseded by HQ's
merge. Old evidence JSON contains pre-PR CI wording; actual prior CI is in the
unchanged PR body. No historical reports or results have been rewritten.

Read/reused M7A.1 and M7B.1 evidence, original PDFs, locked truth/holdout,
codebook/adapter/benchmark, M5/M6 contracts, official six-start archive and M6
identity checks. The 60- and 30-row hashes remain exactly unchanged. DATA-002/003
original versioned deliveries remain unavailable as previously documented.

## What was checked

Every one of the 90 unchanged observations is listed in `M7B1A_VALIDATION.json`
with original code, PDF hash/page/raw line, target horse/race, candidates and
identity status. `M7B1A_TRACK_REGISTER.json` contains all 24 printed codes, country
candidates, source namespaces, unknown validity intervals, official source
references and exact verified observation/date links. A candidate status never
promotes an observation. Verification is restricted to a checked original
historical result plus an independently bound stable-horse chain.

The offline review command reuses the existing semantic benchmark, M7A.1
`official_review`, M6 `resolve`, and existing archived Rikstoto starts. It adds
only bounded official-source checks: structured ATG JSON and individual DNT HTML
result cells. This is not a PDF parser and does not change either existing parser.

- **Seven NO starts:** Custer four, Goffa three. Same stable registration appears
  in checksum-verified original Rikstoto starts and the exact dated/race-numbered
  DNT result row. Country, venue title/canonical URL, historical race header and
  dated photofinish reference are checked. No name-only link. Numeric DNT track
  IDs were not supplied; canonical official venue URLs are preserved, explicitly
  separate from unavailable numeric provider IDs.
- **Ten SE starts:** six existing M7A.1 ATG chains plus Eire once, Beautiful
  Disaster once and Pure Ego twice. Stable ID, pedigree, exact race date/number,
  country, sport, track ID/name and printed-code agreement checked. Eire and
  Beautiful Disaster reuse the already validated M6 target-field/pedigree proof;
  Pure Ego reuses the M7A.1 chain. This bounded retrospective evidence is not
  automatic historical-horse admission. Target-result fields are never read.
- Two additional requested Goffa result pages contain no matching registration
  (11 August Biri; 13 October Momarken). HTTP200 alone is not evidence. Both
  attempts are preserved and no result or venue identity was linked from them.
- All other rows retain candidates or ambiguity. A current code document without
  exact namespace/period evidence is not used to force a VERIFIED identity.

## Measured results / denominators

| Measurement | M7B.1 baseline | This review |
|---|---:|---:|
| Printed codes correct | 90/90 | 90/90 |
| Unambiguous name/country candidates in old register | 43/90 | Original metric preserved |
| Old ambiguous/unverified candidate classifications | 47/90 | 12/47 now source-bound VERIFIED |
| Authoritative observation-specific venue identity | Not measured | 17/90 |
| Existing independent historical result chains | 6 | 17 (11 additional) |
| New VERIFIED / CANDIDATE_ONLY / AMBIGUOUS | Not measured in this taxonomy | 17 / 43 / 30 |
| Conflicting venue evidence | Not measured | 0/90 |

Thus **73/90 are still not VERIFIED**. The new 43 CANDIDATE_ONLY rows are not
necessarily the old 43 candidates: these are different classifications. The
explicit migration table is in the JSON: old 43 -> 5 verified, 37 candidate,
1 ambiguous; old 47 -> 12 verified, 6 candidate, 29 ambiguous. Eight physical
venues are covered by the 17 exact-date checks. All 30 previously locked holdout
rows remain unverified candidates/ambiguities, not silently extrapolated from
known-set results.

B/F/J/S collide across namespaces. The ST index uses Bj for Bjerke, B for
Bergsåker, Ja for Jarlsberg, J for Jägersro, Fs for Forus and Sö for Sørlandet;
Rikstoto NO displays different aliases. **Country of the target race does not
establish country of a historical start.** The L=Lindesberg candidate also has a
historical NO Leangen alias candidate from a secondary program copy. Its
continuous validity is unverified, so L is made ambiguous in this new research
register; the old frozen register is not edited. This is a conservative candidate
classification correction, not proof of an incorrectly VERIFIED earlier venue.
No date ranges or current operation of a historical alias are invented.

The primary ST index was available as indexed official text (2020-05-20), not as
verified PDF bytes: direct public URL returned HTML verification content.
No challenge/access-control bypass was attempted. Primary text supports
namespace candidates only; it does not certify all 90 histories. DNT/ATG result
bodies were actually fetched, hashed and archived. Sources, actual collection
timestamps and hashes are in the fixture manifest and evidence JSON.

## Reproduce / integrity

Using the existing Python 3.12 dev installation, from repo root:

```sh
python -m hbi.history_source_verification --output /tmp/m7b1a-new.json
python -m pytest -q
ruff check .
```

Use an output path that does not exist. The command runs offline against the
pinned original/source archives. In the shared development venv the equivalent
actual invocation used `PYTHONPATH=src .venv/bin/python` so imports select this
worktree. The original external parser replay was also rerun separately using
`hbi.history_semantic_benchmark`; the prior benchmark remains unchanged.

Source fixture: 21 bounded responses, ZIP 237450 bytes, compressed public original
HTML/JSON and provenance manifest. No new full PDF/backfill, production data,
secret or dependency is introduced. The HTML verification response named
`st-index.pdf` is explicitly HTML in the manifest, never parsed as a PDF or called
binary-verified. Archive pinning, individual body hashes, timezone-aware capture
and source/horse/race binding are enforced before verification. A deserialized
CANDIDATE_ONLY/VERIFIED claim cannot promote a row without source validators.

New negative tests cover wrong country, source/hash/timezone, date/race, stable
horse/pedigree, unknown code, invented alias, conflicting result metadata and
candidate promotion. Original Single Lane/Eire/Custer/Goffa/Flying Finn/Pure Ego,
V86/V4, monté and God Only Knows NOT_REPRODUCED regressions remain unchanged.
No global historical identity, model gate or PIT status changes. Close/revert this
additive research PR to roll back; there is no production state to undo.
