# Rikstoto Crawler Pre-winner: research capture V3

V3 is an opt-in collection layer, not a replacement probability model. Legacy
V2 archives and PRE-WINNER Engine v1.0 remain unchanged. Use a **new directory**;
V3 refuses an output containing a legacy PRE freeze.

## Commands

```powershell
python -m rikstoto_crawler.cli capture-v3 --days 2026-09-30 --countries NO,SE,DK,FR --output research-local/capture-v3
python -m rikstoto_crawler.cli weekly-v3 --output research-local/capture-v3
python -m rikstoto_crawler.cli post-v3 --output research-local/capture-v3
python -m rikstoto_crawler.cli watch-v3 --day 2026-10-09 --meeting FO_NR_2026-10-09 --duration 3600 --output research-local/live-capture-v3
```

The meeting in a watch command must actually appear in that day's discovery.
Watch is a bounded local Python process; it needs to remain running. It does not
install a scheduler or deploy a production watcher. `--meeting` on capture limits
a retry/backfill to one meeting. Without `--refresh`, cached successful requests
are reused and failed requests retried. Refresh preserves the first raw response
and writes new revisions. Historical collection cannot reconstruct earlier odds.

## Files and integrity

- `raw-markets/`: original response envelopes, URL, acquisition time, body hash.
- `captures/YYYY-MM-DD/<snapshot_id>.json`: roster, WIN/PLACE, pool availability,
  raw combination odds, provider identities, market normalization and provenance.
- `coverage.json`: current invocation's coverage and fetch failures.
- `weekly/YYYY-Www-market-v3.zip`: one upload per ISO week, manifest and captures.
  Multiple observations remain separate snapshots; the manifest counts unique races.
- `watch-state.json`: T−15/T−5/T−1 observations or explicitly missed windows.
- `raw-results/` and `post-pools/`: separate opt-in official pool payouts.

Capture IDs cover canonical JSON content and source hashes; repeated cached
collection does not rewrite a capture. Weekly manifest hashes are canonical JSON
hashes, not byte hashes. Weekly export can be regenerated as more observations arrive.

## Market gates

V5A maps to canonical V5 while preserving `provider_product` and original `pool_id`.
Every discovered product is recorded, including unsupported and multitrack pools.
WIN and PLACE are assessed independently. An active runner with WIN zero/missing
invalidates whole-field pWIN; PLACE zero/missing does not invalidate complete WIN.
Provider WIN 1.00 can be archived and normalized, without granting execution.
No active runner is dropped to manufacture a complete field. Collective data
requires exact roster coverage, unique numbers, matching race identity and positive
total share. Missing pools never produce pCOL. PRIMARY ≤60 s, SECONDARY >60–300 s,
EXCLUDE_DIAGNOSTIC >300 s remain frozen.

Tvilling/TV, DUO, Trippel/T and DD use public read-only endpoints verified against
the site's service code. Raw lists, zero odds and update times are preserved.
`RAW_SCHEMA_UNVERIFIED` deliberately does **not** assert a complete combination
matrix, executable odds or combination probabilities. Empty responses remain EMPTY.
Multi-race prize payouts are collected only by post-v3. System/alternative values
are attempted separately and retain FETCH_ERROR / EMPTY / RAW_SCHEMA_UNVERIFIED; full-field POST settlement still uses the existing
verified POST workflow. No prize amount is treated as a pre-race input.

## Time and research boundaries

Provider naive timestamps use Europe/Oslo, independently from UTC acquisition time.
T labels require a completed observation within 60 seconds after the target and
before the scheduled start, with all source acquisitions before that start. Late
startup or slow polling produces MISSED, never a reconstructed T snapshot. A changed
scheduled start generates a new checkpoint identity; immutable captures preserve
roster/scratch/start history. The provider's **actual** start is not verified, so a
CAPTURED checkpoint does not establish actual-start PIT validity or execution.
Provider update freshness also needs independent validation before decision use.

No p(win), BET/PASS, stake, Champion, real-money execution or automatic challenger
promotion is added. pWIN/pCOL are market research distributions only. V3 is not
fed automatically into the frozen PRE-WINNER engine.

## Live endpoint smoke, 8 October 2026

Read-only requests for historical 30 September: 59 discovered races across
NO (11), SE (35), FR (8), ES (5); no fetch errors; complete WIN 49, PLACE 46.
Forus alone: 11 races, WIN complete 10, PLACE complete 7. V5A distribution and
TV/DD combination data fetched successfully. V65 prize payouts verified against
the displayed 2,894 NOK / 86 NOK values; DD payout response was empty.
The system-value endpoint returned HTTP 500 for Forus V65 and remains unverified.
QPlus and multitrack V4/V86 remain unsupported. This is endpoint smoke on historical
data, not production collection or evidence of real-time T checkpoint success.
