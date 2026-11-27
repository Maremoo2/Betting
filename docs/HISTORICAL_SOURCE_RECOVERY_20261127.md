# Historical CI source recovery, 27 November 2026

PR #228; audited baseline f82823f48febe30e38dd02551d43d5248a6b1280,
failed run 45964001677. **PARTIAL; not merge-ready.** No acceptance contract,
expected original hash, mandatory replay assertion, strategy or model is replaced.

## Complete dependency register

`CI_HISTORICAL_SOURCES.json` is the machine-readable register: repository,
run/artifact ID, original ZIP filename/SHA, available member filenames/SHA/size,
original upload provenance, dependent workflow steps and test selectors.
It covers all historical downloads in the complete main CI workflow, including
steps after the first failure: 45 original artifacts, of which four also document
the nested provenance of the existing V2 mirror. There are 41 directly consumed
historical objects. A retired legacy original and the current-run independent
handoff are registered separately; neither is silently substituted.

29 ZIPs / 477 members (85,730,135 ZIP bytes) were recovered and verified against
existing original upload digests or authenticated artifact metadata, ZIP CRCs
and exact member hashes. They are retained privately at
`Maremoo2/betting-hq-private-research`, commit
`1deb08459b819ba76af3130a5d28e27317d6243c`, under
`archive/ci-originals/20261127/`. Public Git contains metadata only.

**16 originals: SOURCE_UNRECOVERABLE within the available searched archives.**
No unknown full member list, historical timestamp or missing hash is invented.
Nine of eighteen main original-replay groups have complete retained inputs;
nine require at least one unavailable original. Source completeness is not a
claim that a replay passed. Actual Actions results are reported separately.

## Lost originals and unverifiable claims

| Original run | Missing artifact IDs | Mandatory evidence still blocked |
|---|---|---|
| 41626023709 | 13225524391 | MVP-009 original independent attestation index; retained model sources alone do not attest it |
| 41663427015 | 13244810522 | DEV-012 original Vincennes multipage PDF and starts; original parser regression cannot be reproduced |
| 41814068321 | 13314117015, 13314296054, 13314445420 | Original result scorecard, CORE report and healthy inventory manifest; research-status and health joins |
| 41817026855 | 13315511779, 13315945255 | Genuine inventory outage manifest and false-zero scorecard; real outage recovery classification |
| 41820503559 | 13317420559, 13317520139 | Later inventory/scorecard; original last-known-valid health transition |
| 41826490000 | 13320200641 | Original official outcome join for four pre-frozen scratched-runner cases; model freezes are retained |
| 41832416078 | 13324021063, 13324315724, 13324990108 | Original 65-race no-freeze provenance / joined 16 pairs and 14 WIN triples |
| 41879063497 | 13348981022, 13349320545, 13349440390 | Original 67-race readiness funnel and disjoint source-split evaluation joins |

Run **41820373324**, artifact **13316866794**, is recovered: its original V1
audit (`9ecf547e1792522b15865163bff765c2a87ce90d5220496a7f9f46be369861a6`)
is not lost. The missing other inputs still prevent the combined health replay.
The three first-blocking member hashes remain exactly b14c61c9… (outage),
ecb4477a… (healthy) and be7604e5… (false-zero); full hashes are in the register.

## Recovery scope and stopping rule

Reuse earlier exhausted searches rather than repeat them. Additional searches:
public Git mirror 445 refs / 8,271 objects, private mirror 20 refs / 1,701 objects;
candidate JSON/ZIP blobs and nested archive members; later workflow upload SHA
pins; relevant project/temporary archives (47,753 candidate ZIP members);
22 relevant Downloads files / 70 members; synced project source inventory;
project tar inventory; both repositories' Release inventories (zero releases).
Fresh authenticated metadata queries cover all 45 artifacts. The missing sixteen
return 404. Git/blob and archive searches found known recovered originals, but
none of these sixteen. This is not a claim about inaccessible owner/offline
backups. Further search needs a genuinely new backup location.

## Durable retrieval and privacy

The controlled, isolated stdlib fetch verifies its own reviewed code/catalog
hashes before receiving the existing read-only archive token. It requires the
repository to be private and downloads exact Git-commit paths. Every whole ZIP
and every member is verified. Missing registered sources fail explicitly;
there is no newest-artifact, alternate-hash or network fallback.

CI replay stages receive no archive token and read offline verified bytes.
All mandatory replay commands/assertions remain; independent complete-source
groups run before the first unavailable-source gate so they can be observed.
Neither missing sources nor their dependent tests become PASS.

The existing SQLite handoff now uses authenticated AES-GCM encryption before
public upload. A per-run/attempt key is derived inside controlled fetch from the
existing credential and is never published; the independent job derives it
again, restores every retained ZIP, authenticates/decrypts the exact producer
artifact ID, then applies the unchanged plaintext SQLite SHA, integrity, counts
and migration-ledger checks. No new credential/service or production state.
Prior public artifacts are not rewritten or deleted by this patch.

## Separate reference-cohort proposal — not implemented

If no owner backup exists, request HQ approval for a separately versioned
reference based on the already retained 21 November Jägersro 4/5/6 originals:
Collector 44874876371/14695542768, HBI 44907636310 state 14708117248,
model 14708341778 and report 14708301894. Exact ZIP/member pins already exist
in the unchanged CORE003_AUTHENTIC_REPLAY_V2 contract and this register.
This is archived research, not new prospective predictions or PIT approval.
Genuine new inventory/health observations would also be needed to test an actual
outage; they must not be fabricated from the old lost manifests. Predeclare the
new cohort and acceptance independently. Keep the lost historical claims and
SOURCE_UNRECOVERABLE status explicit. No acceptance change is authorized or
implemented here, and this proposal cannot make the present CI green.
