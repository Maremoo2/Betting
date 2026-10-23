# M7B.1b — semantic gap closure and research exclusion gates

Delivery status: M7B1B_PASS means the bounded investigation, tests and exclusions
are complete, not that all histories are verified or models can use them. Exact
head CI is recorded in the Draft PR/final after actual execution. No merge.

## Preflight / existing controls

HQ had merged #44, #45, #47 and #48. Base/current main at start:
`864d6184474b75cd1de477736552a5b23e1005fe`. #48 reference head remains
`a18acff5aedbdaa4e989f90497ef6a45cd1ac076`. Previous evidence/reports and both
locked source transcriptions are unchanged (60 known, 30 formerly held out).
The latter is now a locked regression set, not a newly unseen holdout.

Reused M7A.1, M7B.1 and M7B.1a evidence, original source bundles, collector record
parser, semantic codebook/benchmark, venue/source verifier and M5/M6 contracts.
Existing controls before this change: pinned archive/parser/member hashes;
original PDF page/raw line/horse-block localization; strict event-date screening;
field missingness/unknown-code preservation; source-bound official venue/race
review for 17 observations; M6's unconditional history-contract/model/PIT blocks.
There were no general research gates named A-E. **Before counts below apply the
same new policy retrospectively to the frozen baseline, not invented old gate
runs.** Betting FFQ1/provider/V3.3/Champion controls remain separate and unchanged.

The existing collector and semantic extraction functions remain unchanged.
`hbi.history_quality.refine_pdf` is a second, versioned normalization stage over
existing records: no header/block/PDF parser. It reads the PDF's existing raw code
and a checked source namespace/table context, not the official result value.
The official source helper only gains strict archive-profile parameters and two
source-confirmed DNT photofinish prefixes (KL and OR). Existing helper defaults,
checks and earlier reports remain unchanged; old source/semantic commands replay
byte-identically.

## Twelve documented gaps, individually classified

All twelve original gaps have source/page/raw-line and before/after evidence in
the gate report, and a separate source-reading control in CONTROL_REVIEW.json.

| Observation | Field(s) | Disposition |
|---|---|---|
| M7A1-003 Custer | DQ | Fixed: NO dg in reviewed NO table and checked historical NO context |
| M7A1-017 Eire | DQ | Fixed: SE placing d, not numeric frd8a decoding |
| M7A1-038 Flying Finn | DQ | Fixed: SE placing d; 5g remains unknown numeric time/rank |
| M7A1-052 Pure Ego | DQ | Fixed: SE placing d; ug grammar still unresolved |
| M7A1-053 Pure Ego | DQ | Fixed: SE placing d; vändg grammar still unresolved |
| M7A1-017/020/038/052/053/054 | Six start methods | Official value exists, reliable PDF method marker does not; deliberately not filled |
| M7A1-052 Pure Ego | Gallop | Intentionally excluded: ug composition not generally validated, no own-event PDF narrative |

Totals: **5 corrected and source-verified; 6 documented but not reliably
represented in PDF; 1 intentionally excluded unresolved composition; 0 gaps left
unexamined; 0 requiring a larger architecture change.** The remaining seven
values are not fabricated. These are five field corrections, not five newly
approved observations or probabilities.

Rules require a freshly checked observation-bound source chain, original raw
code, country namespace and explicitly reviewed original PDF table page.
Reviewed pages are X1 p1 (NO) and X1 p2 / S5 p6 / S1 p1 (SE). This is not a
universal table/country rule. A deserialized VERIFIED claim, another observation
with the same code, or a different source page cannot trigger the upgrade.
Official controls can veto a conflicting extraction; they never supply the PDF
field. Counterfactual tests change official DQ to false: the PDF d rule still
extracts true, then the conflict gate rejects the observation.

## Compound-code investigation

The versioned M7B1B codebook extends, without rewriting, M7B1A's source findings.
frd8a, ug, kubug and vändg retain UNKNOWN_CODE for their full unresolved
composition/time/rank. br in the historical Swedish PDF formatter context remains
unbound; a NO meaning is not transferred to it. Digit-g codes are not numeric
placing/time; explicit decimal placing/time and g markers remain distinct.
Absence of a never implies VOLT, including Pure Ego's separately official VOLT.

A further official Pure Ego start (2026-04-21, Umåker R5) has kmTime.code=u,
galloped=true, placing=0 and DQ **not reported**. Contrast the earlier u/g source
with explicit DQ; absence is not false, and no ug->DQ rule is justified.
No new complete-compound definition is claimed. ST component documentation is
indexed primary text, not verified original PDF bytes; that limitation is
retained. New official result bodies are archived with actual timestamps/hashes.

## All 73 previous unverified venues investigated

Each has an individual venue_review, candidate list, date/race/horse block,
source or explicit research/exclusion reason in the report. Prioritized existing
positive source chains: archived NO registrations, M6 target-field/pedigree
checks, Pure Ego's chain and the existing archived Jägersro target full field
plus PDF age/sex/sire/dam. These are bounded source-context checks for Gate C,
**not Gate D approval**. No new general horse-identity resolver is implemented.

34 new historical source links were verified (12 NO, 22 SE), giving **51/90**
including the old 17. Venue status changes **17/43/30 -> 51/25/14**
(VERIFIED/CANDIDATE_ONLY/AMBIGUOUS). The remaining 39 have explicit exclusions.
Three dated calendar checks found no matching candidate race result (Single Lane
qualifier, Mystic des Thuyas qualifier, King of Ratzeputz 3 October). No nearby
race was substituted. Remaining cases lack a sufficiently bound historical
source chain in the inspected archive/context; candidate IDs or venue names alone
are not proof. Further source/identity work is explicitly pending, not declared
impossible or automatically approved.

A prior M7B1A lookup-routing issue was found: Goffa 11 August / 13 October lines
both print B, but attempted lookups used Biri/Momarken. Those attempts had failed
and approved nothing. Corrected Bjerke searches now bind both original
registrations/date/race; the previous report stays unchanged. Single Lane B is
separately verified Bergsåker. B and all other shared aliases remain ambiguous
at global code level. OA's exact Orkla result uses provider photofinish prefix
OR, not an assumed OA prefix. No continuous alias validity interval is invented.

## Policy and measured gates

The policy is machine-readable, versioned and tested. Reasons accumulate;
SOURCE_VERIFIED, SEMANTIC_VERIFIED and IDENTITY_RESEARCH_CANDIDATE do not remove
any exclusion or confer model eligibility. Each gate requires positive evidence.

| Independent gate/count | Before | After |
|---|---:|---:|
| A exact source integrity | 90 | 90 |
| B complete quantitative PDF core | 53 | 53 |
| B safe explicit unknownness | 37 | 37 |
| C source-bound physical venue/race | 17 | 51 |
| D historical-horse admission | 0 | 0 |
| E PIT admission | 0 | 0 |
| A+B+C jointly | 9 | 33 |
| A+C identity/PIT research branch | 17 | 51 |
| Model eligible | 0 | 0 |

B PASS means source-grounded typed core date/race/distance/method/placing/time;
it is not independent official result truth or model admission. EXPLICIT_UNKNOWN
is a safe valid representation, not an incorrect extraction and not a usable
quantitative value. No absent flag is made false. The strict quantitative branch
requires positive placing/unplaced category and numeric km-time; DQ/qualifiers
with unavailable rank/time are deliberately excluded from that branch, not erased
from source evidence or the A+C identity-study branch.

Sequential attrition: **90 -> A90 -> B53 -> C33 -> D0 -> E0**, before
90 ->90 ->53 ->9 ->0 ->0. Non-exclusive reasons after:

- Physical venue/race unverified: 39.
- Quantitative core unavailable: 37.
- Unknown result/time code: 12.
- Historical horse identity not approved: 90.
- PIT not approved: 90.
- History feature contract not validated: 90.

The report includes every pairwise reason overlap, per-stage excluded observation
IDs, per-horse/date/track/country and outcome distributions. Universal D/E blocks
are explicitly separate from A-C exclusions; they are not evidence of 90 future
events. No actual same-day/future event was found in this sample; negative tests
verify rejection and retain all simultaneous reasons.

## Observed exclusion bias / limits

The fixed diagnostic sample is **not representative** of the 1,605 source lines,
the backfill or future training population. Target-country grouping is not a
historical-country inference; historical country stays UNKNOWN for 39 rows.

- NO targets: 13/20 survive quantitative A-C; SE targets: 20/70. Source coverage
  and existing registration/field evidence favor NO targets in this sample.
- Explicit gallop evidence: 3/18 survive A-C, versus 30/71 with gallop not reported
  (not false). One unknown-code gallop case survives neither quantitative filter.
- DQ evidence: **0/6** survive quantitative B, though all six remain in the
  source-bound identity-study pool. Both qualifiers are excluded quantitatively.
- Every quantitative survivor has an explicit AUTO marker. The conservative
  absence-a rule filters potentially VOLT histories and different text formats.

Using these 33 complete cases as an unqualified training sample could favor
specific countries/venues, automatic starts and clean finishers. This is observed
selection in this diagnostic set plus a plausible future risk, not a measured
archive-wide bias. Future datasets must preserve categorical DQ/DNF/qualification,
missingness and exclusions; never silently train only on complete successful
finishers. This task neither designs nor trains such a model.

## Reproduce / review decision

From the existing Python 3.12 dev installation (new output path required):

```sh
python -m hbi.history_quality --output /tmp/m7b1b-new.json
python -m pytest -q
ruff check .
```

Local shared-venv execution uses PYTHONPATH=src and the existing dev venv. The full
pretty output is reproducible; committed GATE_REPORT.json is the same JSON in
compact form to avoid unnecessary repository volume. The new bounded source ZIP
contains 57 public responses, 488034 compressed bytes; source manifest holds every
original body hash/URL/actual collection timestamp. Existing PDFs/backfill are
not recollected. No new dependency, large PDF, credential or production data.

Control: separate source-reading pass by the **same Codex agent**, with prior
knowledge; not human, blinded or fully independent validation. See the explicit
changed-value source packet and limitations in CONTROL_REVIEW.json.

Recommend **M7B2A_GO for a bounded historical identity/PIT study of the 51 A+C
source-linked records**, keeping all field-specific semantic exclusions and the
39 pending venue records separate. This is a proposed next research scope, not
permission to approve D/E, train or admit features. D needs rigorous historical
identity lifecycle/cross-namespace/full-field evidence and review. E needs actual
feature availability before an explicit target decision cutoff; result retrieval
or a PDF date is not sufficient. All model admission and
HISTORY_FEATURE_CONTRACT_NOT_VALIDATED remain unchanged. Close/revert this
research PR for rollback; no production state changes.
