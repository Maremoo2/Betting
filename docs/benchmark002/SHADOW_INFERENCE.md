# Manual V2 inference — partial, source-gated research

`hbi.benchmark002_shadow` reuses the original BENCHMARK-002 feature function,
softmax, market normalization, log-pool combination, value policy and exclusive
freeze writer. It neither fits a new model nor changes a runtime strategy.

The original 5,274-race benchmark was reproduced byte-for-byte from the preserved
inputs on base `f9cfbd1403ab392d89808d9eea4534b331696b29`. Its terminal-market
combination LL is 1.551608198995003, versus 1.556993940786104 for the fixed
calibrated terminal market. This is exposed retrospective evidence, not a live
probability, executable-price or economic validation.

The latest documented artifact uses the original 2024 fold: fundamental training
through 2022, combination calibration in 2023. Its coefficients and feature order
must be pinned to a SHA-verified artifact. The separate ATG career/season estimator
is a different model and does not receive these weights.

## Two manual phases

```text
python -m hbi.benchmark002_shadow fundamental --artifact MODEL --artifact-sha256 SHA
  --input SOURCE_BOUND_STATE_PACKET --input-sha256 SHA --output NEW_FUNDAMENTAL_FREEZE

python -m hbi.benchmark002_shadow combine --artifact MODEL --artifact-sha256 SHA
  --input ORIGINAL_WIN_ENVELOPE --input-sha256 SHA
  --fundamental-freeze FREEZE --freeze-sha256 SHA --output NEW_SHADOW_DECISION
```

Join each command onto one line in a shell. These entry points use actual UTC
processing clocks and never overwrite existing output. Library clock arguments
are solely for controlled tests and explicit retrospective replay.

The historical demonstration binds Bjerke 2024-01-02 race 1 to original native
registrations and 621 previously observed horse starts. Fundamental and combined
probabilities match the original benchmark within 1e-16. All seven active runners
receive SHADOW_PASS. Historical prices remain non-executable retrospective data.

## Live boundary

PROSPECTIVE mode uses the source-bound V2 adapter described below. Missing
reviewed originals still block inference. A caller-created numeric state or an
asserted canonical row cannot bypass that boundary. The existing historical dataset gate
requires outcome labels and is not repurposed as a live inference gate.

A real Bergen race 1 candidate on 2026-11-19 was captured and tested before its
18:51 Europe/Oslo cutoff. The original program and startlist identify eight listed
horses, seven active. The 35 active-horse form-row candidates are insufficient for
the complete prior-field relative times, historical winner-purse series and
day-delayed opponent graph. Independent permanent identity/scratching evidence
also remains unqualified. No live prediction or WIN request was issued.

Complete artifacts and source receipts are preserved in the local P1-014 output.
There is no scheduler, database writer, stake, BET authority, automatic promotion,
deployment or production adoption in this module. Terminal-price calibration
cannot be transferred to T−4 prices by assertion.

## Integrated manual command: `hbi daily-v2` (P1-019B)

The command is registered in the existing HBI CLI. It reads existing Collector
originals through `collector_handoff.OriginalArchive`, verifies the physical PDF
field and calendar clock, and joins the roster to `v2_feature_state` by native
registration. It never creates a database, schedules a job, retrains a model or
replaces an existing output directory.

The original trained 2024-fold artifact is bundled at
`src/hbi/artifacts/challenger_v2_2024.json`, SHA-256
`cbb9ca7c13032eafc6e639f832f49e2e4cebab0969f501b8170eb62c8853bcf8`.
All nine features and coefficients and the original market/fundamental weights
are read unchanged. An alternate `--artifact` must have the same pinned bytes.
Research dependencies are available with the existing `[dev]` extra; CLI help
does not require NumPy. For an isolated source checkout, put its `src` directory
on `PYTHONPATH` and use `python -m hbi.cli daily-v2`.

```text
hbi daily-v2 --race-id RIKSTOTO:BI_NR_2026-11-20:5
  --collector-root ORIGINAL_COLLECTOR_DIRECTORY_OR_ZIP
  --state EXISTING_FEATURE_STATE.json --state-sha256 EXISTING_SHA256
  --output NEW_DIRECTORY
```

Join the command onto one line. Collector originals must include verified request
records for the raw starts, original program PDF and raw NO/SE calendar metadata.
Request capture times, race identities, hashes and the frozen T−4 boundary are
checked. Unsupported countries, composites, conflicting clocks, unknown input
histories and incomplete active fields stop inference. Full-field output retains
every verified active runner and both runner-specific and race-level blockers.
The command rechecks real time after source loading and clock measurement.

Output is `report.json` and `full_field.csv`. Exit 2 means BLOCKED; no model freeze
or market operation is claimed successful. Current input gaps and the existing
canonical `V2_LIVE_STATE_ADAPTER_NOT_ATTESTED` gate remain effective. A supplied
`PIT_CERTIFIED=true` or `FULL_F3_COVERAGE=true` state cannot authorize a forecast.
`--market-cache` selects a private original WIN archive. No WIN request occurs
before a source-approved freeze; original bytes, SHA readback, provider timestamps
and full-field checks must then pass. Missing source receipts keep this route
blocked. No new attestation authority is introduced here.

Two explicit non-qualified diagnostic modes are supported:

- `--parity-packet FILE --parity-packet-sha256 SHA`: one existing historical
  market-free packet, labelled RETROSPECTIVE_PARITY. It cannot read current
  Collector/state/market inputs. Fundamental p(win) and fair odds are shown;
  there are no combined probabilities, EV or actionable signals.
- `--limited-protocol FILE`: opt in to the already defined
  `V2_OBSERVED_GAP_RESEARCH_V1`. All active horses must still have its required
  observed history/time/prize and source references. Only separately labelled
  conditional probabilities/fair odds are populated. PIT remains false, global
  blockers remain visible and WIN/EV stay disabled.

The real Biri 5 source example lists twelve active horses and reports the two
missing clean-time histories without dropping either horse or inventing p(win).
The authentic Bjerke 2024 parity fixture is preserved under
`tests/fixtures/trained_v2_2024_{packet,expected}.json`; it is copied from P1-014,
not regenerated or fitted. These examples are local implementation checks,
not a repeat of the 5,274-race benchmark or evidence of live betting readiness.

## Reviewed V2 source adapter (P1-020)

`daily-v2` optionally takes `--source-evidence FILE --source-evidence-sha256 SHA`.
This is a manifest of original locations, not permission to certify them. The
existing `admission_originals` review pins remain the sole receipt authority;
this change adds **no real source pins**. Never create or approve a receipt from
a URI, hash format, local timestamp, or caller completeness flag alone. Local
SHA readback proves byte integrity, not independent timing or source authority.

The manifest binds `coverage`, `registry`, `scratchings` and `graph_bundle`.
Each original descriptor requires `uri`, `sha256`, `observed_at_utc` and
`original_file`. `collector_root` is supplied by the command itself. All captures
must be aware, not in the future, and strictly before the frozen T−4 deadline.
Originals must separately pass existing independent review. New roles or source
values never acquire approval automatically.

- Coverage role `V2_STATE_COVERAGE`: `VERIFIED_V2_COMPLETE_STATE_V1`, binding
  physical race/start, exact state/model/graph SHA, Collector source hashes and
  Rikstoto-only policy. An independent review must substantiate complete career
  and opponent coverage and exact-version availability. It must not attest a
  knowingly incomplete observed graph.
- Registry role `REGISTRY_BINDING`: `VERIFIED_V2_REGISTRY_FIELD_V1`, binding
  physical race, exact startlist SHA and every active selection's native
  registration to an authoritative permanent ID, source and version. This does
  not turn a temporary/native registration into permanent identity by assertion.
- Scratch role `INDEPENDENT_SCRATCH`: existing
  `VERIFIED_INDEPENDENT_SCRATCH_V1` format, including all listed selections and
  explicit statuses, verified by `IndependentScratchEvidence`. Shared-feed
  observations do not establish independence.

The adapter rereads original Collector inputs, verifies every graph original
through the existing result decoder, and reproduces the supplied state with
the original day-delayed F0–F3 implementation. Known gaps, unknown result codes,
changed state values, native-ID conflicts and target/future results block it.
No 2025 input is opened. The numerical replay does not establish completeness
or publication timing; these remain separate reviewed source prerequisites.

The model rechecks the 250 ms clock and actual runtime after verification. The
saved `input_packet.json` bytes are exactly those hashed in the exclusive freeze.
A later WIN operation revalidates the freeze's source bindings and unchanged
model output, retains original response bytes with the existing private archive,
and applies the existing full-field/time checks. There is no scheduler, deploy
or authority to bet. Synthetic reviewed-receipt contract tests are not evidence
that a real field has qualified.

On 20 November the Biri 5 source recovery removed both missing clean-time inputs
using complete original Orkla fields. The real before-start attempt still
returned BLOCKED: independent source receipts and complete career/opponent
coverage were unavailable. No real fundamental freeze or WIN read was created.
