# P0 – Independent HQ GitHub approval gate

The technical gate is a read-only evidence verifier; **only an authorized HQ administrator can make it enforceable** by installing required branch protection or an organization/repository ruleset. A workflow file is not a ruleset and does not prevent manual or bypass merges by itself.

## Administrator setup required (not performed by DEV)

1. Restrict who can administer the protected repositories and designate named, independent HQ GitHub **human** reviewers. Record the resulting approved reviewer login list via repository variable \`HQ_REVIEWER_LOGINS\` (comma-separated real logins, not bots or PR authors). The verifier fails closed while the list is absent.
2. Create required branch protection/ruleset on \`main\` in **both** \`Maremoo2/Betting\` and \`Maremoo2/rikstoto-program-collector\`. It must enforce a pull request, at least one independent approval, stale approval dismissal after new pushes, and all required checks on exact PR HEAD. Explicitly add the \`independent-hq-review-evidence\` job as a required status context where this workflow is installed. Install the same read-only gate separately in the Collector; the Betting workflow has no authority over the other repo.
3. Enforce no routine agent/App bypass and verify administrator/bypass behavior with a disposable non-production PR. Independently record the branch-ruleset API configuration and **actual attempted merge rejection** without approval. \`GET /rulesets == []\` does not prove absence of unrelated branch protection; the API returned 403 for prior branch-protection inspection.
4. HQ must approve a particular exact HEAD via GitHub **APPROVED** review **and then** comment this exact single line as the same registered reviewer:

\`\`\`
APPROVED_FOR_MERGE: Maremoo2/Betting PR #<number> HEAD <full-40-character-lowercase-commit-sha>
\`\`\`

5. If the PR head changes, both the review and note must be renewed. \`CHANGES_REQUESTED\` or \`DISMISSED\` after an approval fails the check. Reviewer must match allowlist and must be an actual human GitHub user different from PR author. An \`APPROVED_FOR_MERGE\` note alone is never sufficient. For a new review without a note, the gate stays red.
6. After the real branch rule is configured, test a PR with missing approval and another with a stale commit. Record one successful independent approval transition on a non-production branch and inspect its audit trail. Do not merge a business PR as the test. If the required check is absent from GitHub main protection, the whole governance P0 remains **BLOCKED**.

## Implementation

\`scripts/hq_exact_head_review_gate.py\` evaluates paginated official GitHub JSON evidence and does not authenticate the GitHub identity itself. \`.github/workflows/hq-independent-review-gate.yml\` fetches PR/reviews/comments with **read-only** GitHub permissions. Its success means only \`HQ_REVIEW_EVIDENCE_PRESENT_RULESET_ENFORCEMENT_UNVERIFIED\`. It never means branch protection is installed, software is production-ready, or a person authorized betting. The script contains explicit \`merge_authority=false\` and \`model_or_bet_authority=false\`.

The verifier never inserts approval comments, manipulates review states, merges a PR, updates an active model, or modifies betting data. A GitHub Action status alone is **not** protection until made required by HQ. In particular, already merged PRs #33, #34–#37 (Collector), #101–#102, #105–#108 (Betting) must not acquire fictitious retroactive reviews.

## Reproducible offline negative tests

\`\`\`bash
python -m pytest -q tests/test_hq_exact_head_review_gate.py
\`\`\`

The tests explicitly cover stale approvals, unauthorized reviewer, bot/self-review, later change request/dismissal, missing/forged comment, wrong repository/PR/head, comment before review, and missing configured allowlist. These are *synthetic governance fixtures* and do not prove current GitHub administrators have enforced rules.
