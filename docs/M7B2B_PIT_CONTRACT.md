# M7B.2b historical availability research contract v0.1.0

This is an offline research proposal/validator in `hbi.history_availability`, not
M5/M6 feature admission. Existing M7B.2 gates and
HISTORY_FEATURE_CONTRACT_NOT_VALIDATED remain closed. All outputs have
model_eligible=false. No existing policy is replaced.

## Required fields and time meanings

| Field | Type / meaning |
|---|---|
| event_time | Offset-aware ISO timestamp when documented; NOT_REPORTED otherwise. Historical date is separate, never a fabricated midnight. |
| published_at | Offset-aware ISO only with explicit relevant source evidence. NOT_REPORTED is not zero or event date. |
| first_observed_at | Earliest preserved observation of the **selected exact version**, not earliest public availability ever. |
| source_snapshot_at | Documented acquisition time bound to the source version. This initial contract requires the selected version's first preserved snapshot. |
| decision_cutoff_at | Offset-aware ISO computed from the original scheduled target wall clock, explicit IANA zone and declared research interval. |
| source_version | Original URL, SHA256, archive SHA and member, with matching observed_at. Container/member hashes are distinguished from original HTTP bytes. |
| correction_status | Original as-observed version / unknown prior history / documented change with preserved versions / CORRECTED_WITHOUT_ASOF_VERSION. No negative correction claim from silence. |
| identity_evidence | Stable observation-scoped identity, references, role and conflict flag; retrospective checking is not proof of timely stable-ID availability. |
| availability_evidence | HASH_BOUND_OBSERVATION plus matching reference/hash/time. A printed document date, HTTP Date or claimed publication is insufficient alone. |
| pit_decision | PIT_VERIFIED / PIT_UNPROVEN / PIT_VIOLATION / PIT_NOT_EVALUATED, with all reasons. |

`purpose` must be AS_OBSERVED_INPUT_EVIDENCE and `origin` ORIGINAL_ARCHIVED_BYTES.
Retrospective result labels may be checked after the event but cannot be relabelled
as pre-race input. Raw source lines containing market/prize columns are quarantined
evidence; no feature vector is built. Result labels stay separate.

Unknown publication time does not defeat positive proof that the **exact bytes**
were observed before cutoff. It also cannot create that proof. Snapshot/time/hash
binding, target timezone and role must all validate. An official source saying
`status=results` proves result presence at observation, not the time it became
final, originally published or corrected. PDF CreationDate is self-declared
production metadata, not publication proof. HTTP Date/ETag/Age and ATG's opaque
currentVersion are not promoted to those clocks.

## Decisions

- PIT_VERIFIED: exact selected source has positive hash-bound observation before
  cutoff; role/origin/identity evidence and target schedule/zone are valid; no
  contrary timing/correction evidence. Scope is observed evidence, not validation
  of every semantic cell, officialization or model admission.
- PIT_UNPROVEN: essential evidence/clock/version is absent, or a corrected result
  lacks its required historical as-of version. Unknown never automatically passes.
- PIT_VIOLATION: attempted post-cutoff input/publication/observation/event,
  reconstructed snapshot, label-as-feature, identity conflict, invalid zone/cutoff
  or attempted model admission. Snapshot timestamps cannot be backdated without
  failing comparison to version evidence.
- PIT_NOT_EVALUATED: explicitly outside evaluated scope; no permission follows.

The full official historical-result/identity chain is reported separately from
PDF-only availability. In the actual cohort, 33 old target chains have no preserved
pre-cutoff official version. They are UNPROVEN when excluded, not falsely used.
M7B.2a's 33 conditional violations remain preserved: **using those selected later
snapshots** would violate cutoff. These are different questions, not changed old
results. The 18 earlier future-target scenarios stay visible as baseline evidence;
9 also pass A-C and retrospective D. Neither number admits model features.

## Version and replay rules

Every decision freezes original version references and basis hash. New control
responses and corrections append evidence; they cannot overwrite earlier bytes or
recompute a prior basis using today's response. The frozen replay basis binds the
original parent archive/member, not the changing aggregate review ZIP. Completion
or settlement evidence is separate and cannot supply historical inputs.

This study tests T-24h/T-60m/T-15m/T-4m research intervals, not operational betting
rules. Europe/Oslo and Europe/Stockholm are explicit; nonexistent/ambiguous DST
wall clocks and incorrect offsets fail closed. Missing target cutoff is unproven.
Independent review, validated historical semantics/full fields, lifecycle identity
and a separately approved feature definition remain prerequisites for future
integration. No contract here authorizes training, M8, Champion or BET/WATCH.
