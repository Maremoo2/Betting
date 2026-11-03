# DEV workflow and delivery contract — Betting ecosystem 

**Authority:** A task's explicit HQ mandate is the permission boundary; documentation describes correct behavior but never grants a new write, merge, betting or production permission. This workflow is for `Maremoo2/Betting` and `Maremoo2/rikstoto-program-collector`. Keep model/decision authority in existing policy modules.

## Permission modes
| Mode | Allowed | Never implied |
|---|---|---|
| `READ_ONLY` | GitHub source/log reads; source audit; local reports; authorized local tests | remote code/Sheets/production changes |
| `LOCAL_DEV` | isolated branch/worktree on disk, code/fixture/test changes **locally** | `git push`, remote branch, PR, Actions trigger |
| `PR_AUTHORIZED` | specifically approved GitHub branch/files, commits, push and PR; only within named scope | merge, schedule modification, release, production |
| `PRODUCTION_APPROVED` | **only** exactly named, explicitly project-owner-authorized operation | blanket access to other systems, strategy or wagering |

Betting decisions (`BET`, staking, execution) are a **separate** domain authorization, never a consequence of software delivery approval. Real-money automation remains out of scope.

## Standard single-task loop
| Gate | Required work | Exit evidence |
|---|---|---|
| G0 Scope | Capture task ID, repo/commit, mode, allowed/forbidden paths and acceptance test | unambiguous permission boundary |
| G1 Inspect | Read existing README/docs, actual code and tests; inspect relevant Actions run and source artifacts; identify redundant solutions | links/hashes and specific root cause / hypothesis |
| G2 Reproduce | Run smallest currently failing test or one unmodified PRE fixture; log observed behavior | baseline command/output or honest `NOT_RUN` |
| G3 Implement | Make minimal authorized *local* changes; no policy, model, schedule or provider bypass | small diff and changed-file list |
| G4 Debug | Run focused tests; diagnose stack trace/log; correct and retest within scope | measured red→green or documented blocker |
| G5 Regress | Full suite + lint, provenance/PIT/full-field guard tests, archived E2E and negative tests | actual pass/fail/skip counts; no `SUCCESS=NOOP` substitution |
| G6 Deliver | Produce deterministic input/output hashes, short changelog, known gaps, risk/rollback, test evidence | one complete HQ handoff |
| G7 Stop | `READY_FOR_REVIEW` if criteria met, `REVISE` if fix incomplete, `BLOCKED` if evidence/rights missing | **stop before merge and production** |

Do not request new HQ direction for ordinary debug cycles within authorized scope. Stop for changed scope, new remote write, protected model decision, unresolved external permission, inaccessible source, or safety-critical ambiguity. A correct `BLOCKED` is valid *process* closure but never counts as a successful functional output.

## Minimum DEV report schema
- `task_id`, `mode`, `repo`, `base_sha`, `work_sha_if_authorized`, `source_artifacts` with input SHA-256 and observed timestamp.
- `acceptance_criteria` and `evidence_level`: `DOCUMENTED`, `CODE_INSPECTED`, `TESTED_LOCAL`, `TESTED_CI`, `OPERATIONALLY_VERIFIED`, or `PROPOSED`. Do not collapse these.
- `tests`: command, environment, pass/fail/skip, failure reproduction, expected/actual E2E terminal status, artifact SHA-256.
- `changes`: file list, risk, rollback; `negative_cases` including identity, time/PIT, field completeness and unavailable source.
- `remaining_blockers`, `manual_handoffs`, `terminal_status`; no success claim without actual outputs.

## GitHub technical and one-owner merge contract (MVP-005, 2026-11-03)
- **Agents have zero merge and branch-ruleset-bypass authority.** PR creation is allowed only when explicitly scoped. No direct push to `main`. A DEV task stops before merge.
- Verify the **exact current PR HEAD** and re-run relevant automated technical checks after any new commit: `test` (Ruff, pytest, authenticated original Collector → SQLite → research-model regression), `v1-integrity` and `protected-strategy`. Record failures, skipped tests, source hashes, real artifacts and limitations rather than treating job success alone as operational proof.
- **Only the project owner** may expressly authorize a subsequent merge after reviewing the technical evidence on that exact HEAD. The task mandate to update code or a PR never implies permission to merge, dispatch production workflows, change scheduling, certify PIT or authorize betting.
- Independent human GitHub reviewers, `HQ_REVIEWER_LOGINS`, `APPROVED_FOR_MERGE` comments, and mandatory branch protection/rulesets were retired as **administrative merge conditions** by the owner. They are optional, not merge blockers. This does not waive source originality, independent PIT evidence, temporal gates, strategy protection or BET safeguards. Treat unrelated provider coverage diagnostics separately without misreporting them as PASS.
- Any later production adoption requires its own explicit owner approval and runtime/PIT evidence. Preserve auditability; do not invent or backdate approvals, identities, observation timestamps or evidence.

## Metrics and milestones
- `terminal_report_rate` = tasks with evidence-backed `READY_FOR_REVIEW`, `REVISE` or `BLOCKED` / tasks started.
- `usable_delivery_rate` = accepted functional outputs / tasks started (exclude blocked).
- `manual_extra_handoffs` = HQ interventions beyond initial mandate and final review; `NOOP_SUCCESS` = green runs with zero material work; `unapproved_main_writes` target zero.
- M1: at least 14 days shadow parallel operation; >=95% of source-valid eligible races have traceable terminal status, with fully assessed separately counted; zero invented inputs; one tested archived-data E2E using Betting runtime.
- M2: preregistered paired coverage/completion and/or predictive baseline comparison with PIT/OOS separation; statistical uncertainty recorded; no improvement claim without matched evidence; all current P0 integrity issues resolved.
- M3: at least 30 consecutive days monitored shadow operation, >=98% of *intended material* jobs verified by output/artifact, all P0 PASS, failure alerting + tested fallback to frozen Pre-Watch, explicit HQ go/no-go. This transfers research/analyst workflow, **not betting execution authority**.

## Concrete offline E2E regression target
Use the already archived Bjerke 2026-10-20 race 1, 12/12 runners. Import the existing archive only into isolated local SQLite through `hbi import-races` using a minimally scoped, proven adapter; do not touch the live DB. Full 12/12 field join, no postrace features and no promoted cross-provider ID. Then exercise the existing `betting review` **only with genuinely evidenced inputs**: if full-field WIN, FFQ-1 or calibrated intervals are absent, expect exit 2 plus frozen `allowed=false`, `SHADOW_ONLY`, and a clear reason. Synthetic happy-path fixtures are useful as separate software tests, not proof of a valid historical BET. Repeat with a late timestamp, modified name, corrupt ZIP, extra POST datum and partial odds. Run full tests; do not move the example into prospective model evaluation.