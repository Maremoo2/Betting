from __future__ import annotations

import io
import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com"


def _request(url: str, token: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "horse-betting-intelligence",
        },
    )


def restore_latest_state(
    *,
    repository: str,
    token: str,
    target_path: str | Path,
    artifact_name: str = "hbi-state",
    branch: str | None = None,
) -> bool:
    """Restore the newest non-expired HBI SQLite database artifact.

    GitHub-hosted runners are ephemeral. This makes the previous successful state
    available to the next scheduled run without committing binary databases to git.
    """
    url = f"{API}/repos/{repository}/actions/artifacts?name={artifact_name}&per_page=100"
    with urllib.request.urlopen(_request(url, token), timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    artifacts = [
        item
        for item in payload.get("artifacts", [])
        if not item.get("expired", False)
        and (
            branch is None
            or item.get("workflow_run", {}).get("head_branch") in (None, branch)
        )
    ]
    if not artifacts:
        return False

    artifacts.sort(key=lambda item: item["created_at"], reverse=True)
    latest = artifacts[0]
    with urllib.request.urlopen(
        _request(latest["archive_download_url"], token),
        timeout=60,
    ) as response:
        archive = response.read()

    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        candidates = [
            name
            for name in zf.namelist()
            if not name.endswith("/") and Path(name).name == target.name
        ]
        if not candidates:
            raise RuntimeError(f"{artifact_name} does not contain {target.name}")
        with zf.open(candidates[0]) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
    return True


def main() -> None:
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    target = os.environ.get("HBI_DB_PATH", "data/hbi.sqlite")
    branch = os.environ.get("GITHUB_REF_NAME")
    if not repository or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    restored = restore_latest_state(
        repository=repository,
        token=token,
        target_path=target,
        branch=branch,
    )
    print("STATE_RESTORE=RESTORED" if restored else "STATE_RESTORE=EMPTY")


if __name__ == "__main__":
    main()
