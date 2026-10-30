# P0 archival restored-state read-only E2E – research handoff, 30 October 2026

**Purpose:** Independently check archived **WIN market** probability maps against the odds attached to frozen decisions, recover the exact source market for each exception, find later matching market cohorts, and list open Shadow tickets. This is not a substitute for the existing HBI combined-model `runtime_replay_parity` engine or official settlement.

## What is implemented

- `scripts/p0_archive_readonly_e2e.py` – deterministic stdlib CLI reading an immutable SQLite file via `mode=ro&immutable=1`, SHA-256 verifies unchanged original before/after, records both market mismatches and the exact original source and later odds. It never updates `shadow_tickets`, `decision_provenance` or any V1 audit table.
- `tests/test_p0_archive_readonly_e2e.py` – synthetic controlled tests of exact-source reconstruction, unpriced -0.02 inactive rows, illegal priced extra selections, missing runners, invalid timestamp, missing later cohort, malformed price maps, source-audit cohort mismatch, unchanged DB and output-input path collision.
- CLI is always `p0_status=BLOCKED` with `real_money_authority=false`; independent evidence cannot override the canonical V1 gate.

### Reproduce against a **local** authorized artifact, without any provider/production access

```bash
python scripts/p0_archive_readonly_e2e.py \
  --db /path/to/immutable/data/hbi.sqlite \
  --audit-json /path/to/research-v1/v1-system-audit.json \
  --output /tmp/p0-archive-e2e.json
```

The audit JSON and database must be separately downloaded from trusted GitHub artifacts, hashed and retained with the report. The command must **never** be run against a writable live production database; use an offline archive/copy. `--output` must not overwrite `--db` or `--audit-json`.

## Source evidence independently checked **before** this PR

| Source | Exact reference |
| --- | --- |
| Latest Watcher state | [run 41111189754](https://github.com/Maremoo2/Betting/actions/runs/41111189754); `hbi-state` artifact **13003343590** |
| Extracted SQLite | 531,005,440 bytes, SHA-256 `30b3e281db58589200f123ffae007e5826bf9847bafb21a4302fe505c4bac0c0` |
| Latest actual merged-main systemaudit | [run 41111521341](https://github.com/Maremoo2/Betting/actions/runs/41111521341); audit artifact **13002848843** |
| Main baseline | `6a3c0092f0c3d81058830aadb4df40bd58345652` (merget PR #84) |

Independent read-only SQLite inspection of these archived sources found:

| Scope | Results |
| --- | --- |
| Latest Watcher archived `shadow_decision_runs` | **732** |
| Market-only reconstructable frozen rows (independent check) | **321** |
| Market maps matching saved attached odds | **316** |
| Market maps not matching attached odds | **5** |
| Of the five, exact source market recreates frozen WIN probabilities | **5/5** |
| Of the five, later source cohorts match attached prices | **5/5** |
| Three with known inactive `-0.02` source markers | **3/5** |
| Open Shadow paper tickets | **1** |
| SQLite SHA-256 before/after | **identical** |

The canonical HBI systemaudit in **a different, later runner cohort** reports **305 combined replays checked, 426 skipped, five historical mismatches**, `runtime_replay_parity=FAIL`, and `settlement_integrity=FAIL`. The source state has **732** decisions while the audit checked+skipped **731**. Thus **do not claim the two artifacts are the same pinned database**. The five mismatch IDs nevertheless agree exactly. The script reports the separate denominators and the cohort warning.

P0 open Shadow ticket remains `a55a504a-bc34-487d-aced-75326dcb2b59` for Skive 14.10 race 6, paper stake NOK 25, selection #8; local winner #5. Original complete Rikstoto `isComplete`, status and `Dividends` are not attested. **Do not settle or assume -25 NOK**.

## Milestone evaluation and next gates

| Sub-milestone | State |
| --- | --- |
| Merge PR #80 (PIT/replay diagnostics) | **DONE** |
| Merge PR #84 (stable replay source hashes, source timeline) | **DONE** |
| Independent archived WIN-market source root-cause cross-check | **DONE** on the specific 732-row artifact above |
| Integrate stdlib repeatable archive E2E CLI with tests | **IN_REVIEW** (this PR; CI and independent review required) |
| Run exact merged source CLI against independently pinned archived state | **NOT_YET_SIGNED_OFF**; rerun after PR review and preserve outputs |
| Canonical V1 replay P0 and settlement integrity | **FAIL / BLOCKED** |
| Official Danish result and verified isolated settlement | **BLOCKED** |
| Future CORE-003 PIT / CORE-004 OOS | **NOT_VALIDATED** |

**Related:** [P0 replay #81](https://github.com/Maremoo2/Betting/issues/81), [settlement #82](https://github.com/Maremoo2/Betting/issues/82), [CORE-003 PIT #83](https://github.com/Maremoo2/Betting/issues/83). No paper P/L changes, no Champion/V3.3.12 changes, no auto-promotion, no real-money permission.
