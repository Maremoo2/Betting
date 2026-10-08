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

## Upload to the analysis thread

Each sample/January command automatically writes `<output>/exports/PRE.md`,
`PRE.csv`, `COLLECTIVE.csv` and `PRE-upload.zip`. PRE contains the full runner
table (number, horse, driver, WIN, PLACE min/max, scratches), start time and V/P
turnover. Collective shares and source update times remain in the CSV/JSON files.
The ZIP also includes the original frozen `pre.jsonl` and `freeze.json`.

Archive V2 also displays every collective pool separately in PRE.md: product,
canonical pool ID, leg ordinal from the provider's race-number list, pool turnover,
source URL/update time, full-field shares, normalized pWIN/pCOL, delta in percentage
points and R. COLLECTIVE.csv has one row per runner per pool with explicit
meeting/race/product/leg identifiers, market values, scratches, provenance and
snapshot type. Different pools are never averaged or collapsed. Scratched runners
remain visible with empty probability/share fields and are excluded from normalization.
Machine CSV/JSON retains full precision; Markdown rounds calculated values to six
decimals. Existing V1 freezes remain immutable and have UNKNOWN leg/product metadata
in this new view; re-extract a separate V2 batch from its raw market cache instead
of inventing missing identifiers or rewriting the old freeze.

Observed quality patterns are flagged, not corrected: VP_TURNOVER_IDENTICAL,
PLACE_RANGE_COLLAPSED_ALL_ACTIVE and, for affected Swedish races,
SE_PLACE_SEMANTICS_UNVERIFIED. PLACE semantics remain unverified; these fields must
not be treated as independent Norwegian/French PLACE evidence or p(place).
No M0–M6/MODERATE/EXTREME thresholds are invented. Archive collection beyond the
new five-day integrity sample is on hold pending the user's PRE-WINNER review.

`post` then retrieves the public `/results/raceDays/{day}/raceresults` summary,
including actual WIN/PLACE/TWIN/DUO/TRIPLE dividends with selection and payout
status. It writes separate `POST.md`, `POST.csv`, `DIVIDENDS.csv`, `POST-upload.zip`
and `post-display.json`. Pair/triple dividends retain their combination; they
are not assigned to an individual horse. Refunded/unknown statuses are not
interpreted as winning dividends; missing products stay explicit in JSON.
Summary rows can be published even when the complete-result endpoint is incomplete,
but are labelled UNVERIFIED/QUARANTINED and never qualify settlement. Horse/driver
display names come from the frozen race roster, aligned by provider race/start number.

Regenerate exports offline without new requests:

```powershell
rikstoto-pre-winner export --output research-local/rikstoto-pre-winner/january-2026 --stage pre
rikstoto-pre-winner export --output research-local/rikstoto-pre-winner/january-2026 --stage post
```

For “Rett før start analyse”, upload **PRE.md** or **PRE-upload.zip** first. Upload
POST.md/the POST bundle only after that thread has frozen its PRE assessment.
The PRE export never opens POST files. Uploading both at once defeats the intended
outcome masking. January remains a retrospective archive, not a blind live batch.

These files are local and Git-ignored; source-code/PR links do not expose collected
data. The manual Actions workflow uploads the output as `rikstoto-pre-winner-<run_id>`
under the run's **Artifacts**, retained 30 days. `include_post=true` enables the
separate POST exports after freeze. A workflow-run link can be shared, but artifact
download requires GitHub access; a ChatGPT thread may not be able to read that ZIP
directly. Download and attach the Markdown/ZIP for reliable access. No public site
or permanent raw-data publishing is enabled. This PR has not been merged, so the
new workflow is not yet installed on the default branch.

The expansion gate is fixed before seeing results: >=5 historical days, >=10
accepted races, >=80% accepted among attempted races, >=2 accepted races each in
NO and SE, no unresolved fetch errors and stable repeated archive retrievals.
It permits historical collection only, not model promotion or betting. Every
race still passes its own stricter full-field gate. Unsupported multi-track or
secondary pools are reported; they are not mapped to a guessed race.

## Frozen PRE-only timing integrity

User-confirmed on 8 October: PRIMARY <=60 seconds; SECONDARY >60–300 seconds;
EXCLUDE_DIAGNOSTIC >300 seconds. Existing `contemporaneous<=60` remains unchanged.
`rikstoto-pre-winner integrity --output <archive>` writes the immutable timing
policy/hash tied to the verified PRE file BEFORE computing the diagnostic report.
Outputs under `<archive>/integrity/`: `timing-policy.json`, `report.json`,
`observations.csv`, `PRE-WINNER-integrity.md`. No network requests or POST reads.
Invalid/missing timing, normalization or signal-policy provenance fails closed.
Skew is recomputed from active runners' WIN source times and checked against PRE.

Counts are runner/pool observations and independent race/pool cohorts, not wins
or bets. Races with any PRIMARY pool and those with all pools PRIMARY are distinct.
Historical data never becomes an executable decision snapshot through this rule.
Only existing frozen V3.3 STRONG_POS/STRONG_NEG/NEUTRAL labels are evaluated;
complete PRE-WINNER v1.0 M0–M6/MODERATE/EXTREME remains NOT_CONFIGURED. No POST,
performance assessment, expanded crawl or model changes are authorized by this step.

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
- `/results/raceDays/{day}/raceresults`: POST-only published finishers and dividends.

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
