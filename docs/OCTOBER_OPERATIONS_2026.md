# Daily operational validation, 1–7 October 2026

Status: **IN PROGRESS**, not a completed week. All dates use Europe/Oslo.
The daily check is scheduled at 09:00 through 9 October. The final review follows
the last 7 October race by at least the existing 24-hour settlement grace period.

## What is checked

For Sweden, Denmark, Norway and France, report each day:

- Discovered and already started races, including races with no decision.
- The latest complete-field evidence available **before** the first decision,
  individual identity matches, coverage and explicit rejection reasons.
- Decision status, actual minutes before start, deviation from T−4, and the count
  within 60 seconds of T−4. That band is a reporting measure, not a strategy change.
- Official outcomes, paper tickets, settled tickets and tickets overdue by 24 hours.
- The global settlement backlog, including older tickets that can fail today's audit.

No evidence is UNKNOWN/NO_EVIDENCE. Future days are FUTURE and today's data is
PARTIAL_DAY. Provider coverage passing does not imply model eligibility or a BET.
Missing decisions include unsupported disciplines and provider combinations; inspect
the per-race reasons before calling a gap a supported-race timing failure.

## Reproducible report

```sh
python -m hbi.operations_report --db data/hbi.sqlite \
  --start 2026-10-01 --end 2026-10-07 \
  --output research-v1/october-operations.json
```

This reads the production snapshot without changing it. An absent database is an
error; it must not silently become an empty, apparently healthy database.
The existing daily `HBI V1 System Audit` workflow restores the production state,
runs integrity checks and emits this report even when integrity fails. The full
race-level report is retained in its audit artifact; country/day summaries and the
settlement backlog are printed in the job log. Preserve these dated artifacts.

## Initial evidence, 2 October

Live provider smoke on the merged V2.1 code passed:

| Country | Meeting | Complete active field |
| --- | --- | --- |
| SE | Rättvik | 12/12 |
| DK | Odense | 6/6 |
| NO | Bjerke, 3 October pre-race | 7/7 |
| FR | Vincennes | 13/13, including LeTROT corroboration |

Source: [main live smoke](https://github.com/Maremoo2/Betting/actions/runs/36972395109).
These are **pre-race provider checks**, not a week of production reliability data.
Incomplete Momarken/Orkla fields and an incomplete Bjerke field were rejected.

The [production audit at 08:12 Oslo](https://github.com/Maremoo2/Betting/actions/runs/36972395068)
checked 103 historical decisions: temporal integrity PASS, provider integrity WARN,
replay parity PASS (39 replays), settlement integrity FAIL. The explicit blocker is
ticket `8c02c3e9-b0d7-4714-ba88-05f53e70e183`:
`official_outcome_exists_but_ticket_unsettled_after_grace`.
It remains **OPEN** until official data and settlement reconciliation establish a fix.

The [nightly run for 1 October](https://github.com/Maremoo2/Betting/actions/runs/36936237329)
reported zero tickets created that day, zero settlements and one pending historical
ticket, with zero fetch failures. A successful workflow exit therefore does not
establish successful settlement; its nested integrity status was FAIL.

Production race coverage and T−4 counts must come from the restored-state report,
not from live-smoke counts. Direct artifact retrieval from this local environment
was unavailable (HTTP 403); empty local diagnostic databases are not evidence.

## Completion rule

Finish after data for every day 1–7 October has been checked, missing evidence has
been documented, timing gaps and rejection reasons have been summarized by country,
and settlement through the final race's 24-hour grace has been reconciled. List
unresolved issues explicitly. The calendar ending alone does not mean reliable
coverage, a calibrated model, or demonstrated betting profit.
