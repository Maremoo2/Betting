# P0-SETTLEMENT-001 – primary-source receipt-only verification

Read-only code/CI probe for the historically un-settled **paper** ticket:
`a55a504a-bc34-487d-aced-75326dcb2b59` / `RIKSTOTO:S4_NR_2026-10-14:6`, selected `#8`, original paper stake 25 NOK. Cached outcome winner `#5` is insufficient for a settlement.

## What this delivers

`scripts/p0_official_settlement_probe.py` makes exactly two **GET** requests to the existing public Rikstoto client and records sanitized HTTP metadata (status, URL, response body SHA-256, date and error *kind*); no raw official payload, source participant name, account/token, historical ticket details or DB is uploaded. If both originals are fetched, it runs the existing `settlement_source_review.assess_winner_settlement()` **in memory** to assess only *structural* requirements: complete results, participation/finish, winner and published dividend.

The CI workflow `.github/workflows/p0-official-results-probe.yml` runs on same-repository PR only or manual dispatch; no recurring schedules and no betting/writer invocation. Failures to fetch are recorded as `BLOCKED`, not faked as source evidence. `bookkeeping_authority=false` and `real_money_authority=false` are invariant.

## Prior verified source gap

Actual archive [Watcher 41111189754](https://github.com/Maremoo2/Betting/actions/runs/41111189754), artifact `13003343590`, contains zero complete official `completeresults` and `raceresults` raw payloads for the paper ticket; also [pinned SHA audit 41116541999](https://github.com/Maremoo2/Betting/actions/runs/41116541999) records one open paper ticket. The `provider_fetch_audit` table does not record these result GET paths; that absence alone does NOT prove no GET attempts because `RikstotoClient._fetch()` is not bound to that table.

## Acceptance and boundaries

- Compare CI official GET metadata and response hashes, when any, to authenticated source origins; confirm `complete.isComplete`, selected `#8` participant status and the published positive winning `Dividends`. Failed HTTP or invalid schema are hard blockers.
- A structural PASS here still cannot independently certify a historical settlement: origin/payload hash, human review, policy provenance and an isolated duplicate-safe settlement replay are separate required approvals.
- **Do not** insert or modify `shadow_tickets`, `decision_provenance`, `integrity_audits`, paper P&L, live betting, model/Champion, schedules or protected strategy.
- Review/merge via explicit HQ approval of exact PR head only. No online wager or terminal P0 clearance.

Track [P0-SETTLEMENT-001 issue #82](https://github.com/Maremoo2/Betting/issues/82).
