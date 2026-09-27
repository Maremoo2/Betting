# HBI Strategy Protection

V1 separates ordinary engineering changes from changes to model, decision and
research-governance code.

Protected paths are listed in `.github/CODEOWNERS` and checked by
`.github/workflows/protected-strategy-files.yml`.

A pull request that changes a protected path must carry the exact
`strategy-change-approved` label. The workflow does not add that label itself.

This lets provider, observability, backup, export and test infrastructure improve
without silently changing the frozen Shadow Champion or its decision policy.

The protected set currently covers the fundamental model, probability combination,
decision logic, shadow policy, race rejection, promotion governance and the canonical
machine-readable research-governance document.

CODEOWNERS review enforcement depends on repository settings; the workflow check is
the repository-level CI guard.
