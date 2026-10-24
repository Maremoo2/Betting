# M7B.2c — bounded prospective PIT evidence protocol v0.1

Research-only. No production collector, schedule, database, betting/model pipeline,
Champion or admission rule changes. Every observation/report is model_eligible=false.
The tool delivers capture/replay correctness, not a completed prospective campaign.

## Preflight / source boundary

HQ merged #51. Base/current main checked:
`2d6322148375adb47395e9a9df097fc1c25524de`; reference #51 head:
`dbc4556d86991ddaeab080ac0b7e1a56c243eb06`.
M7B.2a/b contracts, old ledgers, known60 and locked30 remain unchanged. Reused
`history_feasibility.local_instant`, strict timestamp handling, `select_asof`,
existing ATG race-field names and SHA primitives. No new PDF/history parser,
probability model or parallel production store is introduced.

One public calendar request selected two upcoming25Oct2026 trot races: Orkla
NO race1 (`2026-10-25_83_1`,17:52 local) and Umåker SE race1
(`2026-10-25_27_1`,13:45 local). Only the two relevant race descriptors were
retained. TARGET_DISCOVERY explicitly labels its hash as semantic JSON, not raw
HTTP; the calendar is discovery evidence, **not a program snapshot**.

Source URLs are the existing public ATG racing-info race endpoint, restricted to
exact planned IDs, HTTPS and NO/SE trot. No credentials, query strings, redirects,
private/profile endpoints, FR or gallop expansion. The ordinary inherited proxy/CA
is retained; there is no access-control bypass, fallback or automatic retry.
Public endpoint availability is not a licence for unrestricted use; the tool
confers no rights beyond the source's applicable terms.

Each command makes at most two GETs (one per configured role), timeout10seconds,
2MB/body maximum. At most two explicit attempts per race/cutoff, two races and
four cutoffs. No sleep loop, permanent service, cron or Actions workflow is added.
A user must invoke each command; planning is never reported as execution.

## Data minimization and current capture limitations

Only the documented minimal structured JSON field profile is accepted. Unknown
keys, personal/contact/account fields, embedded contact links and opaque PDF/HTML
are rejected without retaining their body. Response errors/statuses remain in
metadata. Original accepted response bytes are never redacted or reserialized.
HTTP Date/ETag/Last-Modified/Age are preserved as metadata, **not publication or
official approval times**. Missing publication remains NOT_REPORTED.

This is deliberately conservative: the existing full ATG card format can contain
trainer/driver/owner fields and other unneeded data, so it is not automatically
cleared for raw storage. No full-card live request was made in this task. A
field-minimized source compatible with the profile, or a separately reviewed
source-contract change, is needed for a real campaign. PDF capture is not claimed
in this version; there is no new competing PDF parser. The live plan's HISTORY
URL is explicitly null and expected runner IDs are unknown. Neither is guessed.

These are source/coverage limitations, not silent filtering into a fabricated
"original" response. No personal data or unrelated raw calendar content is added
to the new evidence fixtures. TEST_ONLY payloads contain synthetic horse labels.

## Plan, observation and clocks

Four research cutoffs are UTC instants computed from an explicit original local
schedule and IANA country zone: T-24h, T-60m, T-15m, T-4m. A declared five-minute
lead window is a **research freshness setting**, not a betting/strategy change.
An observation must finish strictly before cutoff and inside that window to be
selected for the corresponding as-of replay. At/after cutoff is excluded. An
older observation is OUTSIDE_DECLARED_WINDOW, not silently refreshed.

The25Oct targets cross the winter-time transition:

| Target | Scheduled UTC | T-24h UTC | T-60m UTC | T-15m UTC | T-4m UTC |
|---|---|---|---|---|---|
|Orkla25Oct L1|25Oct16:52|24Oct16:52|25Oct15:52|25Oct16:37|25Oct16:48|
|Umåker25Oct L1|25Oct12:45|24Oct12:45|25Oct11:45|25Oct12:30|25Oct12:41|

T-24h is an elapsed24-hour interval, not "same wall clock yesterday". Ambiguous or
nonexistent DST clocks, wrong country/zone, missing clocks and changed source
schedules are rejected or explicitly unresolved.

`registration.json` records actual plan registration UTC separately from the
plan's stated created_at. REAL capture has no clock/transport injection or
observed-at CLI argument. UTC request start and response-completion observation
are recorded by the process; a reversed clock fails. TEST_ONLY injection is
permitted only in explicitly marked tests/demo and cannot become REAL evidence.
These are host-clock observations, not independent time notarization.

Slot status records NOT_OBSERVED or ATTEMPTED separately from actual successful
raw sources and as-of eligibility. A late/error attempt does not fulfil a slot.
A real observation from another attempted slot can only be selected if its actual
time meets the chosen cutoff/window; that never changes NOT_OBSERVED into a
claim that the planned slot was executed. There is no backfill/import of today's
response as a claimed old observation.

## Write-once evidence and deterministic replay

`init` refuses an existing directory. Plan, registration, raw files, capture
manifests and seal use exclusive creation and read-only permissions. Each raw
response and capture manifest is hashed; the final seal binds every file plus
plan hash. Caller must preserve the **external expected seal SHA**, e.g. this PR's
receipt. Replay rejects any changed/additional/deleted file, plan, manifest or
body, including changed metadata. A sealed store cannot accept later captures;
new corrections need a new bounded campaign/evidence version, never overwrite.
Incomplete/crashed captures cannot be sealed and are not claimed as observations.
This is application write-once plus anchored tamper detection, not admin-proof
filesystem WORM. Someone able to change both data and a trusted external anchor
is outside the integrity guarantee; seal.json alone is not a trust root.

Replay verifies the sealed inventory globally, then uses only input-role versions
observed before cutoff and within the declared window. Hash checking excluded
files is artifact integrity verification, not reading their values as features.
CONTROL_LABEL sources and target results hidden in any role are excluded before
input selection. Later corrections cannot change an already sealed replay basis.

Raw bytes/file references stay separate from the small source-field view (race
ID, country, runner IDs). Exact expected full field, unique stable source IDs and
numbers, explicit scratch states, NO/SE trot and unchanged schedule are required
for SOURCE_FIELD_MATCH. Names alone do not verify identity. Missing/partial fields,
collisions, unknown scratch states or absent expected IDs remain unresolved.

Source-byte replay PROVEN is separate from historical-feature replay. Historical
fields materialized/approved: **none**. The existing history adapter/identity/PIT
contracts still need validated source inputs before future use. Gate A can show
verified bytes; B remains HISTORY_FEATURE_CONTRACT_NOT_VALIDATED, C is only a
source-race check, D remains NOT_ADMITTED and E only reports observation timing.
Full historical replay therefore remains REPLAY_NOT_PROVEN; all model gates stay
CLOSED_UNCHANGED. Raw HISTORY role presence is not semantic history verification.

## Actual delivery evidence

The genuine plan has2 races,8 rounds and16 required role inputs (PROGRAM/HISTORY).
**Actual program acquisition attempts0, observed sources0, hash-verified live
sources0, complete historical replays0.** All8 slots are NOT_OBSERVED; all16 role
inputs are missing. Eight HISTORY roles also lack a source URL. No expected full
field is invented. The empty genuine-plan store is intentionally closed/sealed
for an honest reproducible coverage report; it is not a running collection job.
To actually collect later, initialize a new store using the plan, after addressing
source minimization/format/field evidence. Do not attempt to append to the closed
example or assume this session will execute the future times.

The synthetic demonstration is separately TEST_ONLY:4 attempted rounds,5 stored
and hash-verified sources, one source-byte-complete slot,13 missing role inputs,
late inputs and two provider failures. Genuine prospective observations0;
complete historical replays0. Demo results are software verification only.

Genuine prospective collection: **NOT_YET_OBSERVED**.
Complete genuine historical replay: **NOT_PROVEN**.
M7B2C_PASS, if reported after actual tests/CI, applies only to this bounded
implementation and explicit limitations, not to a live campaign or model readiness.

## Reproduce

Python3.12; existing `pip install -e '.[dev]'`; no new dependency. New output paths:

```sh
# Entirely offline, synthetic capture/error/late/missing demonstration:
python -m hbi.prospective_pit_demo --output-dir /tmp/m7b2c-test-only-new
# Replay same sealed demo: use seal_sha256 printed above/in its receipt.json.
python -m hbi.prospective_pit replay --store /tmp/m7b2c-test-only-new/store \
  --seal-sha256 <external-seal-sha> --output /tmp/m7b2c-replay-new.json
# Manual genuine plan registration; this does not fetch or schedule anything:
python -m hbi.prospective_pit init \
  --plan examples/prospective-pit/no-se-2026-10-25.json --store /tmp/m7b2c-real-new
# Only when the bounded source/content prerequisites are met, manually per slot:
python -m hbi.prospective_pit capture --store /tmp/m7b2c-real-new \
  --plan-sha256 <printed-plan-sha> --race-id 2026-10-25_27_1 --cutoff-minutes 1440
# Close a finished or intentionally incomplete campaign; preserve printed hash:
python -m hbi.prospective_pit seal --store /tmp/m7b2c-real-new --plan-sha256 <printed-plan-sha>
python -m pytest -q
ruff check .
```

Two small fixtures provide a TEST_ONLY store and the genuine **unobserved plan**
store. Offline replay reproduces the committed JSON reports exactly, including
actual registration time of the genuine empty store. New experiments naturally
have new actual timestamps/seals; identical-input replay is deterministic.
No result probabilities, WATCH/BET, production writes, merge or M8 admission.
Recommended next research: obtain a compliant minimal program/history source and
independent expected-field evidence, then manually execute a bounded cohort and
archive correction versions before registered cutoffs. No new service is enabled.
