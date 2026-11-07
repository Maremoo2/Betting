# Historical data readiness

## Baseline and sources

The repository comparison starts at Betting main 0536d47c9ffba02cbb1cf3f298237042e9a7457a. PR #171 merged separately. Main already has Phase B source intake, original/frozen WIN diagnostics, prospective outcome scorecards and the synthetic-only MVP-023B prototype. HIST-FORM-001 is a separate offline research export. The replay consumes that existing export and the preserved Legacy annual ledgers. No changes to the provider, historical adapter, runtime tables or strategy paths.

The BENCHMARK-001 reference is a local artifact family under outputs, not a path in GitHub. It contains the First30 original replay, Legacy score ledgers and dynamic development ablations. DEV-009's reported 48-pair scorecard lacks the exact local row set. The three investigated GitHub scorecard archives each had one comparable race, which also appeared in First30. Their union does not reproduce the 48. Reference: https://github.com/Maremoo2/Betting/pull/171#issuecomment-6693222603

## Why model eligibility is zero

HIST-FORM-001 explicitly writes event model_eligible=false. The raw historical result wrapper provides event and collection dates and a hashable content version. The adapter deliberately leaves availability_evidence empty and available_at null. Its independent target-specific gate requires an exact-version, hash-bound, verified receipt or publication assertion earlier than cutoff. The evidence checked here cannot satisfy that gate. This is an input/attestation gap, rather than a reason to change the gate or to backdate an archive receipt.

A source-native registration and exact start-number roster link support historical identity within Rikstoto. They do not attest a cross-provider registry identity. Dead heats, duplicate selection numbers, mismatches and unresolved versions are held out of the full-field replay. Historical official results are label and older-history evidence. They do not attest the target's start-list vintage.

Three different source denominators are 183,961 inventory race IDs, 31,796 exported target races and 15,343 prices examined by the separate decision-price audit. The last audit found zero attested observations at its historical T−10/T−5/T−2 checkpoints. The export contains 328,175 events, of which 304,228 are record eligible for descriptive research and 23,947 are excluded. The previous source ID set check yielded 26,109 fields. The replay adds its stricter version and winner checks.

RESEARCH_RETROSPECTIVE admits only strict source joins for research. PIT_CERTIFIED is reserved for target-specific upstream certification. Every input retains the original source hash, ID, result version and exclusion reason in the immutable export. The replay reports admission diagnostics and counts by year, track, country, source host and status. An absence of evidence remains visible as RETROSPECTIVE_ONLY, PIT_UNPROVEN or MISSING. No protected 2025 payload is needed.
