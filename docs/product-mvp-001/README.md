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
