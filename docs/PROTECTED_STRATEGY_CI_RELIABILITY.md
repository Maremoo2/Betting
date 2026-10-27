# Protected Strategy Files — deterministic PR comparison (27 Oct 2026)

## Incident and verified cause

The `Protected Strategy Files` workflow for merged Betting PR #61 also ran
after `main` advanced. A follow-up run failed with Git exit **128**:

```text
git fetch origin "main" --depth=1
git diff --name-only "origin/main...HEAD"
fatal: origin/main...HEAD: no merge base
```

This is a **Git ancestry/comparison failure**, not evidence of unapproved
changes. A separate earlier run of the same protected-file guard passed.

## Minimal reliability correction

The workflow keeps `actions/checkout@v4` with `fetch-depth: 0`, **removes
the depth-1 refetch**, and uses immutable
`github.event.pull_request.base.sha` and `.head.sha` to find the PR's
actual merge base. It then obtains file names via

```bash
MERGE_BASE="$(git merge-base "$BASE_SHA" "$HEAD_SHA")"
git diff --name-only --no-renames "$MERGE_BASE" "$HEAD_SHA"
```

This is independent of `origin/main` advancing after the original PR
event. `--no-renames` ensures deletion/movement of a protected original
path remains visible, rather than showing only its destination.

If the checkout is shallow, either immutable commit is missing, or no merge
base exists, this step **fails**, never returns
`protected_changed=false` by default.

## What was deliberately kept unchanged

- Exact existing protected strategy/governance file list and its matching
  logic — no added exclusions, renamed paths or weakened filters.
- Approval rule: changes in the protected set continue to require the
  explicit `strategy-change-approved` PR label.
- Bootstrap check is anchored to the **event base SHA**, not a mutable
  remote-tracking ref; same existing bootstrap rule.
- No model, parser, V3.3.12, LIVE provider admission, odds, staking,
  BET/WATCH/PASS or settlement changes.

## Regression coverage

`pytest -q tests/test_protected_strategy_workflow.py` executes the
actual workflow's bash detection stage inside temporary Git histories:

- research-only PR does not request strategy approval;
- a protected engine change still requires approval;
- moving a protected path retains its original deletion in the diff;
- advancing `main` after a PR does not change its pinned comparison;
- missing base SHA, unrelated history, or shallow checkout fails closed.

The protection gate cannot repair the separate French
`NO_FULL_FIELD_LIVE_PASS:FR` provider admission failure. `BET_BLOCKED`
remains unchanged.

### Future hardening (separate explicit-governance decision)

The original protected-path list does not include changes to the workflow
file itself. This PR is intentionally a narrow reliability repair; whether to
place `.github/workflows/*` and the detection logic under a separate
immutable base-branch/governance guard requires its own explicit approval
and non-bypassable review design.
