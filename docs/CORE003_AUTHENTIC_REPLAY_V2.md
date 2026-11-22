# CORE003_AUTHENTIC_REPLAY_V2 — contract design before implementation

HQ authorized this separate replay-contract PR on 22 November 2026. PR #215's
four implementation files remain untouched. This candidate is based on main
f9cfbd1403ab392d89808d9eea4534b331696b29; it is not an approved replacement on main.

## Legacy contract (immutable debt)

LEGACY_REPLAY=NOT_REPRODUCIBLE_SOURCE_EXPIRED. Run 41518035718, artifact
13176561174, SQLite SHA-256
60dbb4d350c252fd1f6dd7d8ba2c19e841153bd0e260318938e1b888bda913b0.
Keep tests/test_collector_handoff_real_archive.py and all its expectations unchanged.
The original upload succeeded with seven-day retention; current metadata/download
are HTTP 404. Preserve docs/P0_CI_REPLAY_RECOVERY_001.md and prior acceptance evidence.

## Old/new controls

| Control | Legacy | V2 proposed coverage |
|---|---|---|
| Source schema | CORE_003_SHADOW_PILOT_V1, original Collector manifest | Same schemas, independently pinned 21 Nov corpus |
| Physical fields | Orkla 1 (7), Orkla 2 (9), Halmstad 10 (8) on 2 Nov | Jägersro 4 (12/11 active), 5 (12/8), 6 (10/10) on 21 Nov, original-verified |
| SQLite | Exact historical state, canonical schema and source rows | Exact independent state, integrity/FK/migrations and original rows checked |
| Source integrity | Original starts/PDF/manifest and archived model SHA | Original artifact ZIPs AND members pinned; no inferred acquisition times |
| Field/reference checks | Full roster, physical PDF clock, retained SQL input, canonical reference | Same existing verify_import implementation |
| Re-import | Identical payload, no duplicate original roster | Same import path, repeated readback, counts stable |
| Research model | Halmstad original MODEL_READY; current archived replay, p sums and report binding | Original 21 Nov research model and current archived replay; full-field probability parity and report binding |
| Strict gates | Independent identity/TMP blockers remain; no PIT/BET | Same gates, explicit rejection assertions |
| Negative cases | Forged report/schema/identity/PIT/BET and unavailable sources | Preserve legacy tests; V2 tests corrupt/missing bytes, late clocks, field/reference conflict, forged report/PIT/BET |
| Separate restore | Local isolated database | New Actions job reopens output bytes and verifies SHA/counts/integrity |

Exact old race identities, historical numerical outputs, and the missing old
SQLite byte hash cannot be reproduced by a different corpus. V2 cannot certify
equivalence of those facts or repair that legacy debt. Historical archived research
may contain ATG-derived snapshots; this tests existing research behavior, not
Rikstoto-only production admission, prospective PIT, or an authorized BET.

## Candidate originals and retention

Collector run 44874876371 / artifact 14695542768; HBI run 44907636310 /
state 14708117248, model 14708341778, report 14708301894. Independent download,
member hashes and exact clocks must pass before acceptance. Do not replace a
missing object with latest state. Preserve exact input ZIPs in a SHA-pinned,
90-day Actions mirror before using it as the normal CI source; finite retention
and its expiry must remain explicit. A missing/expired mirror fails closed.

No model, gate, production workflow, scheduler, or #213 change is authorized here.

## Verified before CI

All four original ZIP digests and the SQLite/member pins in the JSON contract
were verified after independent authenticated download on 22 Nov. The database
has 1,253 races, 8,069 runners, 1,253 provider references, 3,979 provider payloads,
19,265 fundamental snapshots, ten migrations, zero predictions and zero tickets;
integrity_check=ok and foreign_key_check is empty. The old code at its source
commit had eight migration scripts; its actual missing database ledger cannot
now be verified. No missing legacy ledger is inferred from the new state.

The chosen cohort has 34 listed runners and 29 active runners. All three archived
fundamental models are MODEL_READY. Only race 4 is RESEARCH_READY: races 5/6 are
already SOURCE_BLOCKED in their original reports due to missing WIN. V2 must
reproduce these statuses, never manufacture the missing market. The archived
information time is 2026-11-21T13:12:07.300862+00:00 (14:12:07.300862 Europe/Oslo).
Starts are 14:36, 15:00, 15:22 Europe/Oslo. These times remain original assertions;
current re-execution is explicitly ARCHIVED_REPLAY, not a prospective prediction.

The new tests cover fresh insertion (by removing only the three import receipts
in a disposable test copy), idempotent existing-row readback, conflicting stored
payload, original corruption, wrong artifact provenance, missing original,
missing-mirror fail-closed behavior, late source observation, incorrect full-field
name, missing canonical reference, forged PIT/BET and import-receipt rejection.
No test copy mutation is written back to the original SQLite or original ZIPs.

The CI candidate also checks pinned #215 code separately. This compatibility
job is restricted to this replay PR branch and does not replace #215's registered
checks or constitute HQ acceptance of the proposed contract.

## Pinned source mirror and explicit retention limit

The bootstrap PR CI run 45062690629 executed the real V2 replay successfully
on commit 48a6f18d842d86d0de833d325fdc56c9d760435e, then uploaded the exact four
original ZIPs without changing their bytes. Mirror artifact 14769603393 has
ZIP SHA-256 c3b6b3a24f1bfc861060015a378bc891d7c48925ce8242be633a246e5829df75.
It was independently downloaded locally; all four inner original ZIP hashes
must still match the original run/artifact pins in the JSON contract.

The final proposed CI source is this exact mirror, never latest state and never
an automatic fallback to a different source. Configured retention is 90 days;
current expiry is **20 February 2027 20:46:57 Europe/Oslo**
(2027-02-20T19:46:57Z). This is finite Actions retention, not permanent storage.
Before that horizon HQ must review a byte-identical, independently verified
retained copy and its new location, or CI will fail closed. The same old seven-day
state is not silently assumed available. The bootstrap mirror is only uploaded
when the reviewed contract explicitly has mirror=null, not on normal future runs.

This is a proposed CI dependency change only. The new corpus does not restore
2 Nov data or authorize merge of either PR. HQ must review and explicitly adopt
the exact contract before #215 can be accepted on it. After owner adoption,
#215 needs its own required checks on the new main-based test contract; this
PR's compatibility job does not rewrite #215's currently failed check status.
