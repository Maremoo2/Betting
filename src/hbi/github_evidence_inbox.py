from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .intelligence_bridge import BRIDGE_VERSION

ENVELOPE = BRIDGE_VERSION


@dataclass(frozen=True)
class GitHubEvidenceInbox:
    repository: str
    issue_number: int
    token: str

    def _request_json(self, url: str) -> list[dict[str, object]]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "horse-betting-intelligence",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub evidence inbox fetch failed: {exc}") from exc
        if not isinstance(payload, list):
            raise TypeError("GitHub evidence inbox returned a non-list payload")
        return [row for row in payload if isinstance(row, dict)]

    def read_rows(self) -> list[dict[str, object]]:
        owner_repo = urllib.parse.quote(self.repository, safe="/")
        output: list[dict[str, object]] = []
        page = 1
        while True:
            url = (
                f"https://api.github.com/repos/{owner_repo}/issues/"
                f"{self.issue_number}/comments?per_page=100&page={page}"
            )
            comments = self._request_json(url)
            for comment in comments:
                body = comment.get("body")
                if not isinstance(body, str):
                    continue
                rows = parse_bridge_comment(body)
                for row in rows:
                    enriched = dict(row)
                    enriched["_github_comment_id"] = comment.get("id")
                    enriched["_github_comment_url"] = comment.get("html_url")
                    enriched["_github_comment_created_at"] = comment.get("created_at")
                    output.append(enriched)
            if len(comments) < 100:
                break
            page += 1
        return output


def parse_bridge_comment(body: str) -> list[dict[str, object]]:
    text = body.strip()
    if not text.startswith(ENVELOPE):
        return []
    raw = text[len(ENVELOPE):].strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []
