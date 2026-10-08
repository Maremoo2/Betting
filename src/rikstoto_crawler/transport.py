"""Scoped GETs, bounded retry, caching and checkpoints adapted from MSFT-crawler."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

HOST = "https://www.rikstoto.no"
KEY = r"[A-Za-z0-9]+_NR_\d{4}-\d{2}-\d{2}"
PATHS = (
    r"/results/racedays/\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}/list",
    rf"/racedays/{KEY}/(?:starts|raceInfo)",
    rf"/results/raceDays/{KEY}/(?:totalInvestment|scratchedStarts)",
    rf"/game/{KEY}/betdistribution/(?:winodds|placeodds)/\d+",
    rf"/game/{KEY}/betdistribution/investment/V(?:4|5|64|65|75|85|86)\?raceNumber=\d+",
    rf"/results/raceDays/{KEY}/\d+/completeresults",
)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    """Atomic checkpoint/report replacement; market freezes use a different writer."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                   allow_nan=False) + "\n", encoding="utf-8")
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            # Windows scanners/readers can briefly lock a checkpoint during rename.
            # Retain the previous complete file; never truncate it to work around a lock.
            if attempt == 5:
                raise
            time.sleep(.05 * 2 ** attempt)


class ArchiveClient:
    def __init__(self, root, *, delay=0.3, timeout=20, retries=2):
        if delay < 0 or timeout <= 0 or not 0 <= retries <= 3:
            raise ValueError("invalid bounded request policy")
        self.root = Path(root)
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.last_request = 0
        self.requests = 0

    def get(self, path, *, result=False, refresh=False):
        if not any(re.fullmatch(pattern, path) for pattern in PATHS):
            raise ValueError("URL outside read-only Rikstoto scope")
        is_result = path.endswith("/completeresults")
        if is_result != result:
            raise ValueError("result endpoint forbidden in PRE stage")
        cache = self.root / ("raw-results" if result else "raw-markets") / (
            sha256(path.encode()).hexdigest() + ".json")
        if cache.exists() and not refresh:
            stored = json.loads(cache.read_text(encoding="utf-8"))
            if stored["path"] != path or stored["body_sha256"] != digest(stored["body"]):
                raise ValueError("cache integrity mismatch")
            return stored
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            self.requests += 1
            request = urllib.request.Request(HOST + "/api" + path, method="GET", headers={
                "Accept": "application/json", "User-Agent": "HBI-PRE-WINNER-read-only/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if not response.url.startswith(HOST + "/api/"):
                        raise ValueError("unexpected redirect outside API")
                    body = json.load(response)
                if not isinstance(body, dict) or body.get("success") is False or "result" not in body:
                    raise ValueError("unsuccessful provider envelope")
                stored = {"path": path, "url": HOST + "/api" + path,
                          "fetched_at": datetime.now(UTC).isoformat(), "body": body,
                          "body_sha256": digest(body)}
                if refresh and cache.exists():
                    # Preserve the first retrieval; refresh is a separate stability observation.
                    revision = cache.with_name(cache.stem + "-" + digest(stored)[:16] + ".json")
                    write_json(revision, stored)
                else:
                    write_json(cache, stored)
                return stored
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == self.retries:
                    raise
            time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("retry exhausted")
