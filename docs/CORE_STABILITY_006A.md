# CORE-STABILITY-006A — offline Phase A contract and candidate finalizer

Development only. No network, Sheets writer, scheduler, new model integration,
production freeze, or betting authority. Do not deploy this code as a finalizer
of record. It only produces an offline validation candidate.

## Existing code reused

- Collector main `544bab4b78672f23df11a3ab0e0e7d13729de5ee`:
  `collector/prewatch_ready.py` canonical encoding and selected source projection,
  `prewatch_ledger_reader.py` completed physical ID concept,
  `prewatch_shadow_mailbox.py` independent recheck semantics (30-second limit).
- Betting `prewatch004_pack.validate_phase_a_draft` and `SCORE_BOUNDS` are reused
  unchanged; its JSON schema remains the nested draft contract.
- Existing Champion gate: total >=70, data >=15, shape >=10, mispricing >=18,
  liquidity >=8. No market, p(win), EV or new thresholds.

## Contract

`adapt_ready_packet(packet, expected_packet_sha256=...)` accepts the **nested**
Collector diagnostic/replay packet (not the mailbox wrapper), bound to an
expected canonical hash from a separately trusted carrier. This verifies
consistency, not independent original-byte provenance or a signature. The
original Collector verification remains required. It maps the selected race to
the existing DRAFT validator's input shape, checks official/PDF identities,
scratches, driver changes, both source receipts, active history, and original
deadline. No new parser or model-feature certification.

The new `CORE_STABILITY_006A_DRAFT_V1` envelope contains exactly:

- schema, packet_sha256
- draft: unchanged PREWATCH004_PHASE_A_DRAFT_V1 object (all scores and reasons
  required for candidate finalization)
- sports_first: selection_id (string), horse_name (exact official name)
- mispricing_candidate: selection_id, horse_name, hypothesis, counterargument;
  nested draft candidate must equal "#<selection_id> <horse_name>", and nested
  counterargument must match
- history_refs: active selection IDs mapped to nonempty lists of SHA-256 hashes
  of exact UTF-8 raw history text for those horses

Hash references prove membership, not interpretation quality. No string-based
heuristic can certify that every sports argument is true or market-free.
Source-only instructions and human/research QA are still required.

`evaluate_test_candidate` takes explicit simulated TestRechecks and reference
time. Rechecks must bind packet, newest run, roster fingerprint and fresh
observations; completed physical races are excluded. Deadline is exclusive,
compared without truncating microseconds. The original receipt clock is never
extended by rechecks. No test timestamp is a real freeze. Classification is
a preview only. Missing score evidence fails closed; valid below-gate output
is BELOW_THRESHOLD preview, not a stored Phase A.

## Tests

`pytest -q tests/test_phase_a_contract.py tests/test_phase_a_finalizer.py tests/test_prewatch004_pack.py`

All newly committed fixtures are explicitly synthetic and conform to the
Collector test fixture shape. Existing original archive tests are unchanged.
A genuine independently verified Ready Packet replay, original-byte provenance
and prospective output quality remain distinct acceptance gates. No actual
private packet is committed to Git.

## Remaining gates

006B/006C: authorized independent runtime clock/rechecks, signed or trusted
handoff/return path, production-quality output QA, immutable freeze carrier,
writer credentials and exact idempotent updateCells/readback/RunLog. This
module does not grant any of these. An externally supplied TestRechecks object
must NEVER be used as live evidence. No production key, freeze_ref or Ledger
row is emitted. Never turn an offline preview into an operational signal.

Rollback: close the draft PR / discard the development branch; no production
change or migration is needed.


Collector's bare `build_ready()` output can omit the publication flag in replay
mode. An explicit publication flag must be false. The scheduled start is
minute-precision source evidence. Actual start and live checks require a
separately authorized live evidence path. Physical race IDs supplied in
simulated Ledger rechecks are compared in Unicode NFC.
