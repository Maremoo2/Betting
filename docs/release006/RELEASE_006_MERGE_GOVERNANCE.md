# RELEASE-006 · Merge governance

MERGE_GOVERNANCE=WEAK. The authenticated repository response showed administrator access and allow_auto_merge=false. GitHub returned an empty active-rule list for main, an empty repository ruleset list and HTTP 404 for classic main protection. The existing workflow requires strategy-change-approved on protected diffs, and CODEOWNERS lists protected paths. No server-enforced required check or code-owner approval was observed. The identity or exact UI/API route used for each historical merge was not established.

Both PRs merged with zero labels and a failing protected-strategy check on their exact heads. [PR 187](https://github.com/Maremoo2/Betting/pull/187) · [Check](https://github.com/Maremoo2/Betting/actions/runs/43007199156/job/130477514678) · [PR 188](https://github.com/Maremoo2/Betting/pull/188) · [Check](https://github.com/Maremoo2/Betting/actions/runs/43026491099/job/130542396283)

The protected diffs between the prior main and the two merge commits change shadow runtime deadline, hold and research persistence behavior. The reviewed diffs leave Champion weights, PREWATCH, probability/decision thresholds and staking policy untouched.

Owner recommendation. Apply a main ruleset requiring pull requests and the protected-strategy check from GitHub Actions on the current revision. Require the other mandatory checks, dismiss stale approvals, restrict bypasses and validate enforcement with a controlled failing draft. This audit performed only read operations.
