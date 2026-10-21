# AGENTS.md — Maremoo2/Betting 

## Purpose and authority
Betting is the intended main analysis/decision engine. The Rikstoto program collector supplies source evidence; ChatGPT Pre-Watch V3.3.12 remains a frozen comparator until a separate, evidence-based HQ transition decision. Existing HBI Shadow Champion/watcher is a **research comparator**, not a V3.3 or Pre-Watch-authorized BET.

HQ's **specific task authorization** controls permitted actions. Repository instructions never grant GitHub, workflow, production, Sheets, model, staking, or betting execution authority. Without explicit permission, READ ONLY on remote systems and LOCAL ONLY for requested drafts/tests. Conflicting instructions or unclear scope: stop and report.

## Read before writing
1. `README.md` and `ARCHITECTURE.md` — map the existing code; do not treat documented claims as runtime evidence.
2. `docs/BETTING_V3_3.md` — active Betting decision contract and FFQ-1; `docs/RESEARCH_GOVERNANCE.md` and `docs/research_governance.json` — research authority.
3. `docs/DATA_CONTRACT.md` and `docs/INTELLIGENCE_BRIDGE.md` — PIT/provenance and evidence-only import.
4. Relevant implementation in `src/betting/`, `src/hbi/` or `src/pre_winner/`, existing `tests/`, and `.github/workflows/ci.yml`. Read `docs/STRATEGY_PROTECTION.md` before touching protected paths.
5. Common process: [`docs/DEV_WORKFLOW.md`](docs/DEV_WORKFLOW.md). Do not create a parallel strategy/policy module when an existing one serves the task.

## Workflow — complete the authorized scope before returning to HQ
Define input → observable acceptance → negative cases. Reproduce the issue from a specific commit/run or archived PRE fixture. Make the smallest local change in a disposable workspace; run focused tests; debug using actual failures; rerun focused tests; run full `python -m pytest -q` and `ruff check .` (when dependencies available); execute one end-to-end contract case and negative cases. Log command, exit code, passed/failed/skipped, input/output SHA-256, remaining blockers and changes. A missing test runner is `NOT_RUN`, not PASS. Avoid routine HQ interruptions when still within scope.

## Safety invariants
- No result/closing odds/poststart data in a before-start input; no guessed provider identities, timestamps, scratches, odds, full-field cases, probability bounds, or PLACE estimates.
- Reuse existing canonical import, PIT/full-field gates, runtime, settlement and V3.3 review. An intentionally blocked replay is valid **test behavior**, not `FULLY_ASSESSED` or a BET.
- No changes to Benter logic, V3.3.12 gates, thresholds, staking, Champion, frozen decisions, model training or operational schedule without a new explicit HQ authorization.
- A `SUCCESS` workflow with `NOOP`, skipped steps or no artifacts is not operational success.
- Never push/merge to `main`, enable auto-merge, bypass branch rules, write Sheets, create automations, run production workflows or place bets. A branch, commit or PR is allowed **only** when HQ explicitly authorizes that operation; a PR does not grant permission to merge.

## Exit report
State `READY_FOR_REVIEW`, `REVISE` or `BLOCKED` with a verifiable reason. Include repo/commit, diff, source hashes, chronological test evidence, end-to-end terminal status, unresolved P0 findings, artifact IDs and rollback. Stop before merge. Actual production adoption requires an independently recorded HQ approval bound to the exact PR head SHA and enforced GitHub controls.