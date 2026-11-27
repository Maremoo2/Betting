# CORE-STABILITY-006A-QA-02 — private evidence reader pilot

Status: development-only, transport approval pending. No original ZIP or private
locator is in this repository. No credentials, network access, workflow changes,
or production activation are introduced by this draft.

The manifest pins the original MVP-016 upload metadata from job 126460564343
and the existing CI member SHA. An unavailable Actions artifact is not proof
of the cause of its absence; 21-day retention is independently observed.

The reader accepts ONLY the exact 575-byte artifact 13304793845 and one member,
cohort-index.json, with independently fixed hashes. It does not extract arbitrary
paths, accept alternate manifests as authority, or silently substitute data.
Synthetic security tests exercise only verification primitives, not original
evidence or live authentication. The staged ZIP must be obtained separately
from an explicitly approved carrier with independently enforced access controls.

## Pending owner decision

Use an existing private carrier, preferably isolated same-repository CI with
read-only contents scope and reviewed pinned code. Do not expose private
repository tokens to untrusted code in public pull requests. No private uploads
or permission changes are authorized by this draft. The carrier, reader identity,
retention rules and approved access path must be decided and verified separately.
The original public CI gate remains unchanged and failing until an approved
equivalent evidence path is integrated; private pilot success alone is not
public CI success.

## Planned runner pilot after approval

Stage the exact ZIP into a trusted temporary directory. Run:
```
python -m hbi.original_evidence_recovery --manifest docs/original_evidence_manifest.json --source-zip <approved-staged-zip> --output-dir <new-dir>
MVP016_EMPTY_COHORT_ORIGINAL_ROOT=<new-dir> pytest -q tests/test_mvp016_empty_cohort.py
```
Verify all nine tests and no phantom race/error. Test missing authentication
and carrier access independently. The existing CI SHA pin remains mandatory.
Before combining with PR #227, use an isolated integration branch with both
exact reviewed heads and no merge to main; record both SHAs. Never expose
private original bytes in logs/artifacts on the public repository.

A genuine original-backed runner and subsequent full CI remain pending.
