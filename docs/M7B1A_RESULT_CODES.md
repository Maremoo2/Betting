# M7B.1a — source-bounded result-code verification

This is a new research codebook version (`M7B1A_RESULT_CODEBOOK.json`, 0.2.0), not a
rewrite of the frozen M7B.1 codebook/parser or either PDF reference. All original
codes remain byte-for-byte in their source records. Five evidence layers stay
separate: PDF transcription, unchanged semantic adapter, official historical
result, retrospective identity proof and UNVERIFIED PIT.

## Eleven requested families

| Family | Source-grounded conclusion | Remaining limit |
|---|---|---|
| frd8a | ST defines frd component. Exact Eire ATG791286, Axevalla8, 19 July R10 has DQ=true, kmTime.code=frd8 and auto start | Complete concatenation/digit meaning unverified; UNKNOWN_CODE, never eighth place/68 seconds |
| dg | Exact Custer DNT registration578001020205025, Bjerke 12 September R3: labelled disqualified for gallop, raw dg | Scoped NO result category/reason; not universal Swedish rule; no numeric placing/time |
| br | DNT result examples explicitly label br/BR as did not finish | Full br ag formatting for PDF's historical SE start not bound; leave that PDF compound unknown; no cause/time inference |
| ug | ST documents u and g components. Pure Ego ATG793918, 10 October 2025 R6: code u, gallop=true, DQ=true | Full compound grammar unknown; row flags verified separately |
| kubug | ST documents kub/u/g components. Beautiful Disaster ATG794752, Åmål29, 9 August R4: code kubu, gallop/DQ=true | Full chain/cause inference not approved; UNKNOWN_CODE |
| vändg | ST describes turning and not completing. Pure Ego, 26 October 2025 R6: code vänd, gallop/DQ=true | Compound remains UNKNOWN_CODE, not numeric time/placing |
| d | ST placing-cell definition is disqualification; corroborated by exact ATG results | Not automatically a reason, numeric rank or cross-country mapping |
| digit-g | g documents gallop; original 5g/4g/8g are time-cell codes, not decimal times | Complete digit meaning unknown; never turn into final numeric placing/time |
| 0 | Exact Goffa official zero rows, separate from labelled DQ rows, support unplaced category | No numeric finishing rank or automatic DQ; does not prove why unplaced |
| qualification | Contextual k + gdk means approved qualification | k elsewhere can mean distance; no newly verified official qualifier result row |
| missing/non-numeric time | it definition is no timing; official compound kmTime.code fields are not numeric | No zero/null substitution or digit extraction |

Seven of eleven families have **scoped** documentary component/category evidence;
four compounds are PARTIALLY_DOCUMENTED (`frd8a`, `ug`, `kubug`, `vändg`). This is
not seven newly approved universal parser rules. In particular br remains unknown
for the unbound PDF context; digit-g's numeric part remains unknown. Family
occurrences overlap (placing d and nonnumeric time can refer to the same start),
so their counts must not be summed as unique starts.

Each entry lists actual original-PDF occurrences, page/hash/raw line and raw codes.
For missing/non-numeric time, 13 of the selected 90 rows have nonnumeric/unreported
numeric time. Additional literal it examples are located in the original PDFs,
explicitly outside the 90-row denominator and never added as benchmark outcomes.
All definitions distinguish documentary evidence, scoped official-row outcomes
and unresolved composition. The primary index document is indexed text only;
its binary was not retrieved. DNT/ATG raw response bytes and hashes are preserved.

## Independent historical crosscheck and adapter limitations

Seventeen distinct starts, seven NO/ten SE, were reviewed. Six are existing M7A.1
checks and eleven are new. Stable registration/ID and pedigree evidence is required;
name matching alone cannot pass. Every link remains bounded to its original PDF
observation/date. No identities or values are propagated to other histories.

Within the official subset there are **zero demonstrated PDF/official value
conflicts and zero incorrect extracted adapter values**. Twelve additional
source-backed values are not extracted by the unchanged adapter:

| Observation | Missing source-backed fields |
|---|---|
| M7A1-003 Custer | DQ |
| M7A1-017 Eire | Start method, DQ |
| M7A1-020 Beautiful Disaster | Start method |
| M7A1-038 Flying Finn | Start method, DQ |
| M7A1-052 Pure Ego | Start method, gallop, DQ |
| M7A1-053 Pure Ego | Start method, DQ |
| M7A1-054 Pure Ego | Start method |

These are omissions/intentional exclusions, not twelve false guesses. The PDF gold
has UNKNOWN/NOT_REPORTED where appropriate and stays unchanged. Official VOLT for
Pure Ego does not make absence of a a valid VOLT extraction rule. Any future
adapter update must consume an explicitly provenance-bound evidence layer or a
validated namespace-specific rule; it must not silently backfill PDF gold.

An initial review diagnostic called Custer's start method a conflict because its
DQ time cell lacks a; this was a comparator/source-reader limitation, not a PDF
conflict. Reading the exact official race terms provides explicit Autostart. The
reviewer was corrected to read those terms and to count absent official values
as missing, not as contradictory values. Both raw sources and unchanged PDF
values are retained; no parser was adjusted to make this result green.

## Control level, PIT and next decision

`M7B1A_CONTROL_REVIEW.json` records source-first checks on ambiguous codes,
qualifications, DQ/gallop/zero and NO/SE references before implementation of this
source audit. The controller was the **same Codex agent**, with prior task
knowledge, not a human or a blind independent second reviewer. No normalized
parser answer was used as source truth during that pass. Independent human
sign-off remains absent. No broader accuracy claim is made from this risk sample.

All observations remain RESEARCH_ONLY, model_eligible=false, PIT=UNVERIFIED.
Retrospective official results may support labels but collection time does not
prove historical feature availability. Existing HISTORY_FEATURE_CONTRACT_NOT_VALIDATED
and every production/provider/model rule remain unchanged.

**HQ recommendation: M7B2_HOLD for general feature integration.** There are still
73 unverified venue observations, four unresolved compound families, an unbound
br formatter context, missing qualifier-result corroboration and twelve adapter
omissions. First resolve the required namespace/code rules or explicitly exclude
these features, and obtain an independent source review. A later narrowly scoped
historical identity/PIT study can use the 17 documented chains as evidence, but
this PR does not authorize model-feature admission or broad M7B.2 rollout.
