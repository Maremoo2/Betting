# MVP-021 P0 | Prevent a partial cumulative benchmark after GitHub API 403

## Actual independent failure, 4 November 2026

[Ordinary CORE-003 41898656060](https://github.com/Maremoo2/Betting/actions/runs/41898656060) on unchanged main `4fe98264522e8453589a83bda6d9e59c53b22147` reported workflow-level SUCCESS, but source-recovery logs at 19:40:24–19:40:31 UTC contained repeated:

`error fetching artifacts: HTTP 403: API rate limit exceeded for installation`

and `DEV011_ORIGINAL_ARCHIVE_DOWNLOAD_BLOCKED:<artifact-name>`.

Original DEV011 manifest: artifact **13357447410**, original `manifest.json` SHA-256 `2f8f0341808be0e5f19346f0a24b33126714152b6ae5bf3cf671c3bf83fbe63b`. Although GitHub pagination successfully inventoried **4,234** artifacts over **43** pages, only **112/308** selected archived originals were recovered. Of the selected 308, **191** were missing/unverifiable through runtime source download and **5** were old unindexed legacy. **Zero** pinned result races could be checked. Its workflow nevertheless wrote scorecard artifact **13356948878**, index SHA `763b0adcb566064d8422f64186ff6561e5a325a1a821939db15e211c850f569f`, with artificially reduced partial **52 physical / 22 full-fields / 18 scored pairs / 17 WIN triples**. The scorecard even reported generic `INCOMPLETE_ORIGINAL_COVERAGE`, not explicitly `SOURCE_DOWNLOAD_OUTAGE`.

The last separately verified source-recovered benchmark is [ordinary 41897182938](https://github.com/Maremoo2/Betting/actions/runs/41897182938), scorecard artifact **13356727378**, SHA `9a0fee8f93640dd348e4c4e8310b0383ea790b873e702010e0ddecba4fe55521`: **88/38/28/27**, 0 PIT. Its original DEV011 manifest artifact **13356852314**, SHA `a9aaa04da898267c478061a4ba5c93d0146e97c5f850c1f87d83e53efc986aa4` recovered **300/306** selected originals; its remaining legacy/original deficiencies are recorded, not falsely repaired.

**Root cause:** `src/hbi/mvp016_inventory_guard.py` treated only `PAGINATED_GITHUB_INVENTORY_UNAVAILABLE` as a hard source outage. The CORE-003 workflow printed failed individual `gh run download` requests but never passed their failure state to the scorecard guard. A complete *list of source objects* is not proof that the bytes of every selected original were actually downloaded.

## Narrow, controlled repair

1. The unchanged `gh api --paginate` full-inventory source selection stays untouched.
2. Before all downloads, the existing CORE-003 workflow creates `dev011-coverage/download-failures.tsv` (metadata-only). Each actually failing `gh run download` appends `source_run_id<TAB>artifact_name<TAB>kind` to it; the file is uploaded together with the ordinary coverage manifest and never contains raw source bytes.
3. The existing `mvp016_inventory_guard` now fails closed when this file is missing, malformed, references an unselected artifact, has duplicates or contains **one or more confirmed failures**. It compares failures to the exact manifest selected originals and reports a SHA-256 of the receipt and failure count.
4. A failed source run emits only `dev009-outcome-scorecards/source-unavailable.json` with `BLOCKED_SOURCE`, the explicit reason `ORIGINAL_ARTIFACT_DOWNLOAD_UNAVAILABLE`, unknown counts (`null`), and `prior_verified_scorecard_invalidated=false`. It **does not** publish a new `index.json` or claim that the old benchmark fell.
5. When all downloads succeed, the empty receipt is valid. Existing historical missing/unindexed originals remain separately diagnosed under unchanged DEV011 rules; normal scorecard processing continues. Existing paginated-inventory 403 hardgate stays intact.

## Regression and acceptance

Unit regressions cover two legitimate failed GETs (actual original run/name pairs), empty successful receipt, 5 malformed receipts, absent receipt, known preexisting historical missing original, and previous paginated-inventory outage. A read-only optional original replay pins the 418986 manifest bytes by SHA and confirms the 4,234/43/112/0 original counters. It never uses inferred races, model probabilities, winners or PIT.

**No source relaxation, no backfill, no retroactive model freeze, no Champion/CORE004/V3.3.12, odds/BET/WATCH/PASS, canonical SQLite/settlement or automations touched. `bet_authority=false`.** Draft PR requires exact-HEAD CI and explicit owner merge approval.

## Architecture-level remediation (not implemented)

The GitHub App per-artifact source GET pattern exhausts installation API rate limits in repeated ordinary CORE-003 runs. The long-term source archive must be immutable owner-approved storage (object lock/WORM, SHA256/UTC original receipts, least privilege, short-lived credentials, read-back tests) or a rate-budgeted authenticated cache that verifies exact source bytes before use. No deploy or quota bypass in this patch. A green provider smoke does not prove archived source retrieval worked.
