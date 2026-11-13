# Betting HQ daily briefing

The report is read-only and uses a single CORE-003 cohort from the requested date. It verifies the ledger pin and joins the cohort, Collector handoff, CORE-003 and archived SQLite by their existing hashes. It keeps archived research scores apart from the daily cohort. Race ordering is based on verified full-field model availability, then full WIN coverage, then scheduled time. Archived Champion WATCH/PASS labels are shown as research, and the report has no BET authority.

## Existing functionality

Champion and CORE-004 already publish full-field estimates and model versions in frozen shadow originals. The Research Ledger preserves archived scores and current blocked observations. The Observatory measures source health and calibration in SQLite. The operations report reads decision and ticket evidence from SQLite. Nightly computes shadow settlement summaries and writes them to SQLite, so this briefing does not invoke it. The current report originals do not supply a validated daily P/L, CLV or operational decision journal. No approved SMTP or mail delivery workflow was found in the inspected Betting workflows.

## Manual preview

Run with Python 3.12 in the Betting environment. Supply ZIPs from the same Actions run and extract the archived pilot SQLite separately. Obtain the ledger index SHA-256 from its trusted run receipt. Historical examples are optional and use an independently pinned Research Ledger output and the extracted archived model directories.

```text
python -m hbi.hq_daily_report --date 2026-11-13 --run 43417750508
  --ledger 14033032924.zip --ledger-sha 178e1ea5e3f766251572d8427bd9e23a74a910d458502f416b2f04ddc13f5e83
  --core 14032618909.zip --cohort 14033416787.zip --handoff 14033042749.zip
  --collector 14033017998.zip --db pilot.sqlite --output report
  --archive revised-archived-after.json
  --archive-sha 16c5b33f224b42f5fbef68979f5d07767da41f9d9d716f902ccd7fcd728c9fa1
  --archive-run 41911371831 --models models
```

Enter the command on one line or use your shell's continuation syntax. The example contains six real races from [CORE-003](https://github.com/Maremoo2/Betting/actions/runs/43417750508), three with complete captured WIN fields and none with an accepted model. The [historical example](https://github.com/Maremoo2/Betting/actions/runs/41911371831) is an existing pre-start Solvalla freeze. It gives no predictions for the current cohort. The report JSON preserves source status codes.

## Delivery

The command produces HTML, plain text, JSON and a multipart EML file. Open the EML in a mail client that supports importing it as a draft, review the text and HTML, and select an approved recipient. An optional explicit recipient sets only the To header. Generation performs no network calls, creates no outgoing messages, and repeated generation sends zero emails.

Daily delivery still requires an approved sender and recipient, a daily time and authenticated transport configuration outside the repository. The eventual sending job must use a persistent idempotency key for report date and recipient and reuse it on workflow retries. Manual MIME preview has been tested. Live transport has not been configured or exercised.

## Eskilstuna, 13 November

The meeting view uses the full Collector manifest, independently pinned earlier model cohorts and the existing run ledger. It recovers the original race 1 research freeze from [run 43411672945](https://github.com/Maremoo2/Betting/actions/runs/43411672945), cohort artifact 14030497831. Its cohort index SHA-256 is 29f54a5d659ab8b7224e64f954bcf8111cc6cbd88744d1ab2b0e1c62f84b455d and its model SHA-256 is 1374609d712dc75cbe246f60b7ad381c29b05411a5fce8f6dcaa87b9aaaa7d2f. Use `--meeting S1_NR_2026-11-13 --prior-cohort 14030497831.zip 29f54a5d659ab8b7224e64f954bcf8111cc6cbd88744d1ab2b0e1c62f84b455d --prior-run 43411672945 --report-at 2026-11-13T12:25:00Z` with the current source arguments. The archived model uses the original 11:20 UTC start and 11:16 UTC cutoff. The later archived schedule lists 11:29:30 UTC.

Collector discovered 8 Eskilstuna, 10 Kalmar and 7 Biri physical races. The inspected 11:40 UTC CORE-003 cohort contained Eskilstuna 2–6 and Lyon-Parilly 5. Its absence of Biri and Kalmar does not establish a discovery failure. CORE-003 prefetch sorts its eligible candidates by time and race ID without a country preference. This PR limits changes to the report view.

For automatic operation, publish the meeting view from the existing Collector manifest and import all verified pre-start cohorts for that date. Keep original ZIPs and their SHA-256 receipts in approved durable storage before Actions expiry. DEV-009 can then attach official results to archived freezes and score the same field. The current run has a source-unavailable DEV-009 diagnostic, so this report does not claim an official result or durable automated delivery.

## MASTER BUILD 001

The updated Eskilstuna and NO/SE examples use Europe/Oslo for every displayed timestamp. JSON preserves the original UTC values. In the original model run 43411672945, Collector's morning PDF and archived /racedays body gave 12:20 Oslo. The hash-linked CORE-003 report (14030522773, member SHA-256 26c6eba80b9dd3796bfbbd575850161e89f74b0a7b542bbb34f40a19f7168746) recorded the same canonical and earliest retained start and a cutoff of 12:16 Oslo. The model original was calculated at 11:50:29.353646 and written at 11:50:29.354070 Oslo. The later pilot SQLite first records the revised 12:29:30 value at 12:40:01.627882 Oslo. The retained source event includes a body hash; its response bytes are absent. The user-reported 12:29 display has minute precision; its rendering rule is unverified. The exact later calendar value gives 12:25:30 if applying four minutes for comparison, with no change to the original cutoff.

The complete Rikstoto result independently records startTime 12:30:28 Oslo (body SHA-256 dc6fbace98659b4b429f9de8713d43e023b8b3362dcd1ad317445fadb21f99b0). The result and raceday endpoints agree that number 3, I'm a Bad Boy, won. DEV-009 rejects scoring with OFFICIAL_LATE_SCRATCH_NOT_FROZEN because Habanos and Pompom were active in the frozen model and marked Str in the official result. The freeze remains a pre-cutoff research observation. Both full distributions sum to 1, and the displayed fair odds and EV reproduce the archived observations for all 11 runners. Habanos had only two historical starts and was later scratched, so the displayed theoretical EV provides no realized return observation.

Use --nordic for the physical Norwegian and Swedish trot meetings in the Collector manifest, --timing-core ZIP SHA256 to verify the original cutoff for a model, and --official-result RACE_ID DIRECTORY for separately retained complete and raceday JSON originals and their receipts. The later run 43426741239 supplies Eskilstuna 5–8 observations. The report covers 25 original fields (Biri 7, Eskilstuna 8, Kalmar 10), four complete WIN snapshots and one model freeze. The prefetch horizon is 90 minutes and the task cap is four. At the Eskilstuna runs examined, the evening meetings were outside that horizon. The same day's archived evidence does not establish that an otherwise qualified Nordic race was displaced by a French race; collection order is untouched.

The local delivery includes a verified 20-member ZIP export. Original model bytes and later official result bytes have separate paths and SHA-256 entries. A re-read verified every entry and the original freeze digest. The ZIP is outside Git, and automatic retention or recovery after actual Actions expiry has not been exercised. The existing pilot archive is retained seven days in Actions. Model, Collector and research artifacts generally have 21-day retention in this workflow. DEV-009 already evaluates immutable originals against separately archived official results. The report also shows a distinct historical Solvalla example with original outcome and all three scores and leaves the existing benchmark unchanged. No calibration conclusion or new model candidate is derived from the single Eskilstuna example.

An automated delivery job still needs a private archive destination and a review of access and retention, a consistent source inventory through expiry, and after-race import of verified results. The EML remains a manual preview. No external message was sent.

## P0-NO-SE-FIRST-001

The isolated CORE-003 source queue now allocates its existing budget to Norwegian and Swedish trot as one tier, followed by Denmark, France and other markets. Within a tier the ordering is existing urgency, valid roster, complete timely fundamentals, time to start, action and race ID. The capped T−4 source receipt queue applies the same market tiers to its existing eligible set, then uses the existing effective deadline and race ID. The fixed cohort still records all eligible physical races and model admission evaluates all cohort members under the existing gates. Other prefetch callers keep the original ordering. Discovery, collection limits and model admission are untouched.

The pinned archived SQLite and CORE-003 reports reproduced all four original provider actions exactly in two saturated runs. In [43411672945](https://github.com/Maremoo2/Betting/actions/runs/43411672945), the four slots change from two Eskilstuna and two Lyon-Parilly tasks to four Eskilstuna tasks. The original Eskilstuna 1 WIN and fundamental tasks stay selected. In [43417750508](https://github.com/Maremoo2/Betting/actions/runs/43417750508), the two Lyon-Parilly tasks give way to fundamental acquisition for Eskilstuna 2 and 3. Biri and Kalmar were already discovered and their evening starts were beyond the 90-minute horizon at both runs. See nordic-queue-replay.json for original hashes and exact before/after lists. These are scheduling replays, with no counterfactual model claims.

The updated Nordic report draws on the latest completed run available at capture [43450228274](https://github.com/Maremoo2/Betting/actions/runs/43450228274) and earlier pinned cohorts. The most recent fixed cohort contained only Danish Skive races at that hour. The meeting denominator stays anchored to the Collector manifest: Biri 7, Eskilstuna 8, Kalmar 10. All 25 have archived start fields. All 8 Eskilstuna races have an observed model disposition across the reviewed runs. Race 1 has the original 11-runner research freeze and a later official result which is unscorable under the unchanged scratch gate. Races 2–8 were rejected. Five Eskilstuna races have complete captured WIN snapshots. The report does not infer evening meeting outcomes ahead of their starts.

For automatic results, preserve each run's originals and SHA receipts in the private local export before expiry. After official publication, use DEV-009 to fetch both existing Rikstoto endpoints, check physical race and frozen active field, retain the result receipts separately and calculate scores only for admitted pairs. Feed the scorecard into Research Ledger and Observatory. Result revisions remain separately archived, and disagreements stay blocked under DEV-011. The original Solvalla benchmark is shown separately in the report. No automatic operation was activated.
