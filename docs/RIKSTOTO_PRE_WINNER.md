# Rikstoto Crawler Pre-winner

Historical read-only market crawler. Entry point is the user-created root file
`Rikstoto Crawler Pre-winner`; implementation is `src/rikstoto_crawler`.

Technical starting point: [Maremoo2/MSFT-crawler](https://github.com/Maremoo2/MSFT-crawler),
inspected commit `ac3e30bc4494766c27bb7826ed46a1fd557df88f`. The adaptation follows
its separation of scoped fetcher, pure extractor, structured storage, checkpoint/
resume and per-item error report (`src/async_crawler.py`, `src/storage.py`). Microsoft
HTML extraction, RAG/chunking, login/browser fallback and broad link-following are
not applicable here; the new transport is a small dependency-free API adaptation.
The Microsoft repository is unchanged. No third-party source code was copied.

## Run in the required order

```powershell
pip install -e ".[dev]"
python "Rikstoto Crawler Pre-winner" sample --output research-local/rikstoto-pre-winner/sample
python "Rikstoto Crawler Pre-winner" january --sample research-local/rikstoto-pre-winner/sample --output research-local/rikstoto-pre-winner/january-2026
# Results are an explicit, separate stage AFTER the PRE freeze:
python "Rikstoto Crawler Pre-winner" post --output research-local/rikstoto-pre-winner/january-2026
```

Equivalent installed command: `rikstoto-pre-winner`; module:
`python -m rikstoto_crawler.cli`. Historical sample defaults to 22–26 December 2025,
NO/SE/FR, two collective-market races per meeting. `--days`, `--countries` and
`--max-races-per-meeting` select a sample; zero means all applicable races.
January covers 1–31 January 2026, all applicable races in the sample country scope.
No daily scheduler is enabled. The manual workflow can run sample-only or sample
plus January and uploads the complete research archive, including interruption
checkpoints. GitHub's job limit can interrupt a month crawl; resume locally from
the downloaded archive with the same output directory/configuration.

The expansion gate is fixed before seeing results: >=5 historical days, >=10
accepted races, >=80% accepted among attempted races, >=2 accepted races each in
NO and SE, no unresolved fetch errors and stable repeated archive retrievals.
It permits historical collection only, not model promotion or betting. Every
race still passes its own stricter full-field gate. Unsupported multi-track or
secondary pools are reported; they are not mapped to a guessed race.

## Verified read-only API paths

All requests are GET on `https://www.rikstoto.no/api` and allowlisted:

- `/results/racedays/{from}/{to}/list`: date/meeting/race/pool discovery.
- `/racedays/{day}/starts` and `/racedays/{day}/raceInfo`: roster and race metadata.
- `/results/raceDays/{day}/scratchedStarts`: historical scratches.
- `/game/{day}/betdistribution/winodds/{race}`: full archive WIN prices, NOT the
  winner-only dividends array in the result endpoint.
- `/game/{day}/betdistribution/placeodds/{race}`: historical PLACE min/max ranges.
- `/game/{day}/betdistribution/investment/{product}?raceNumber={pool-start-race}`:
  historical V4/V5/V64/V65/V75/V85/V86 shares. Select the returned leg using exact
  race number AND race key; preserve the canonical pool key.
- `/results/raceDays/{day}/totalInvestment`: V/P and collective pool turnover.
- `/results/raceDays/{day}/{race}/completeresults`: POST stage only.

The collective/turnover/scratch paths were observed in the public frontend service
bundle `chunk-GX4YOHCS.js` on 8 October 2026, loaded by `main-ESTEPZ3S.js`, then
live-verified. Old guessed producttimeline/program URLs returned 404 and are not
used. Raw turnover is minor units; divide by 100 for displayed NOK. For Bordeaux
26 December race 1, raw V=114307500 and P=84455200 match displayed 1,143,075 and
844,552 NOK. Raw values and scale remain alongside the conversion.

## Data gates and research boundaries

Every accepted race must be finished/non-abandoned, have exact race+start-number
roster identity, explicit scratch status, unique horse IDs, positive finite WIN
for all active runners, valid PLACE ranges, complete active shares in >=1 pool,
and positive unambiguous V/P and collective turnover. Duplicate runners, missing
legs or mismatched race keys fail closed. `isMerged` is preserved as a provider
flag: historical Swedish finished races routinely expose true while their complete
rosters/prices match exactly; it is not used as evidence that a race was cancelled.

Temporary foreign horse IDs permit race-local market alignment and are explicitly
marked unstable. They do NOT qualify lifetime fundamental history, cross-race
horse joins, provider-country activation or the production FULL_FIELD_ONLY cohort.
This crawler does not change HBI's provider resolver or database.

WIN is normalized over active runners: `(1/odds)/sum(1/odds)`. Normalize each
collective pool over the same active set, then compute Δ and R with the frozen
V3.3 research divergence labels. No fundamental p(win), PLACE probability, BET,
stake or settlement is generated. Market probabilities are not fundamental input.

Source update times, retrieval times, URLs and canonical body SHA-256 hashes are
stored. Dates without a timezone follow the existing Rikstoto Oslo contract.
The first accepted race in each meeting is refetched (WIN, PLACE, collective) to
check archive stability. **Stability of a finished historical archive is not proof
of exact bet-close timing or executable pre-race availability.** The API does not
provide a universal finality certificate. Snapshot kind is HISTORICAL_TERMINAL_ARCHIVE;
`executable=false` and `prospective=false` are mandatory.

Multi-race shares lock at the first leg; WIN for a later leg can be hours later.
Preserve these source timestamps and WIN/collective skew. <=60 seconds is labelled
contemporaneous; later-leg comparisons remain archive research, not V3.3 decision
snapshots or price-verified historical bets. PLACE ranges are not a realized PLACE
payout. No P/L or CLV is invented from these archives.

## PRE freeze and POST

`raw-markets/`: scoped raw API cache with acquisition timestamp/hash. Cache keys
are path hashes; refreshed stability observations do not overwrite originals.
`pre-rows/`: checkpointed market-only extraction. `checkpoint.json`: completed IDs,
rejections, network failures and stability evidence. Finished crawls emit immutable
`pre.jsonl` and `freeze.json` with content/file hashes; `quality.json` summarizes
accepted/rejected coverage. Different scope requires a new output directory.

The PRE extractor allowlists fields and never reads official finish positions,
winners or dividends. Only AFTER `freeze.json` exists and file hash matches can
`post` fetch result endpoints into `raw-results/` and emit `post-results.json`.
POST requires `isComplete=true`, every active runner, matching start number and
horse name (only known country/display suffixes normalized), and an official winner.
Provider IDs must agree. For a race-local TMP ID with a blank result ID only,
unique matching names across the complete field permit explicit race-local alignment;
this is labelled separately and never becomes a stable horse identity. Contradictory
nonempty IDs or ambiguous names fail closed. Incomplete results remain quarantined.
PRE stays unchanged.

This is an outcome-masked **retrospective** reconstruction, never a prospective
blind batch. The example's winner was already discussed in the analysis thread.
The available conversation reader returned only its five latest turns and no
older cursor; the complete M0–M6 and MOD/EXTREME definitions were not retrievable.
They are explicitly NOT_CONFIGURED, not invented or inferred from winners.
Data extraction and V3.3 evidence are implemented; full PRE-WINNER strategy
variants require the original frozen protocol before any M0–M6 backtest is claimed.

No production DB writes, model/Champion changes, real-money route, automatic
promotion or merge are part of this crawler job. See the
[dated smoke report](RIKSTOTO_PRE_WINNER_SMOKE_2026-10-08.md) for
actual historical/January counts; synthetic tests do not count as live evidence.
