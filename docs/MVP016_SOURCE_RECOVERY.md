# Exact MVP-016 original recovery

The original 575-byte ZIP from run 41796128435 / artifact 13304793845 was
recovered locally. Its ZIP digest matches the original upload job 126460564343:
`2b2683ba14774b637237f99484f1b8256321744c0552c0d30a5635bd549a6cfa`.
Its sole member, `cohort-index.json`, retains the existing mandatory CI pin
`ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0`.
ZIP CRC, exact member list, member SHA and original empty-cohort semantics are
checked before extraction. The existing replay and expected values remain.

## Private durable source

Betting is public. No original bytes are committed or published there.
The approved private repository `Maremoo2/betting-hq-private-research` stores the
unchanged original as a versioned Git blob, selected by exact commit
`eb4f479bd90f31fcfd3d2d07b92f14179442c98b`, not latest/main. The path and source
pins are in `MVP016_SOURCE_ARCHIVE.json`. There is no Actions retention expiry.
The original local ZIP is preserved as a separate copy.

This is authenticated retention, not WORM storage or an independent timestamp
authority. Repository administrators can delete the repository or references.
The pinned commit and SHA checks fail closed on deletion/change. Private Git
does not itself create any independent identity or PIT approval.

Public PR CI requires `RESEARCH_ARCHIVE_READ_TOKEN`: a fine-grained token with
only Contents: Read access to that private repository. No write permission,
account credential, production token or token literal is needed. Store it only
as a Betting Actions secret. Fork PRs receive no secret and fail closed.
Rotate/revoke through GitHub; token expiry must not silently select another
source. The fetcher verifies that the source repository is still private and
downloads the exact pinned Git object over the authenticated GitHub API.
Original bytes are not printed or uploaded in public diagnostic artifacts.

The private archive's separate fresh-runner readback verifies the same Git
commit and original hashes without depending on expiring workflow artifacts.
The existing canonical SQLite independent readback is also preserved: its
unchanged producer steps now run before legacy archive steps so unrelated
historical source failures no longer hide the independent readback result.
No mandatory legacy step is skipped, removed, softened or called PASS.

## Scope of authenticity

The recovered index is genuinely empty, with no admitted physical race/model.
It references three upstream hashes (report, database, Collector handoff).
Those bytes are **not members of this ZIP**. Their hash strings are preserved
and checked against the original; this is not independent re-verification of
the external bytes. The recovery receipt explicitly reports
`all_upstream_bytes_verified=false` until their originals are found and checked.
Successful empty-cohort replay must not be reported as restoration of a missing
historical SQLite database, model original, or full upstream source chain.

Other mandatory historical replay sources can independently remain expired.
Overall CI is PASS only if all mandatory steps actually pass; source download
failures remain CI_BLOCKED_SOURCE. Neither this original nor canonical V2
readback substitutes for those other cohorts or changes Phase 1's frozen live
contract, source, window, model, policy or hardgates.
